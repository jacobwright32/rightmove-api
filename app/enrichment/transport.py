"""Transport distance enrichment service.

Uses NaPTAN CSV data (free, no auth) for rail/tube/tram/bus stop locations,
plus static airport/port dicts.  All distances computed offline via
haversine + scipy.spatial.cKDTree — zero API calls at query time.
"""

import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree

from ..config import NAPTAN_CACHE_DIR, NAPTAN_CACHE_PATH, NAPTAN_MAX_AGE_DAYS

logger = logging.getLogger(__name__)

NAPTAN_CSV_URL = "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"

# ── NaPTAN StopType codes ────────────────────────────────────────
STOP_TYPE_RAIL = "RSE"   # Rail Station Entrance
STOP_TYPE_METRO = "TMU"  # Tram/Metro/Underground Entrance
STOP_TYPE_BUS = "BCT"    # On-Street Bus Stop

EARTH_RADIUS_KM = 6371.0

# ── Static data ──────────────────────────────────────────────────

UK_AIRPORTS: list[dict] = [
    {"name": "Heathrow", "lat": 51.4700, "lon": -0.4543},
    {"name": "Gatwick", "lat": 51.1537, "lon": -0.1821},
    {"name": "Stansted", "lat": 51.8860, "lon": 0.2389},
    {"name": "Luton", "lat": 51.8747, "lon": -0.3683},
    {"name": "London City", "lat": 51.5053, "lon": 0.0553},
    {"name": "Manchester", "lat": 53.3588, "lon": -2.2727},
    {"name": "Birmingham", "lat": 52.4539, "lon": -1.7480},
    {"name": "Edinburgh", "lat": 55.9508, "lon": -3.3726},
    {"name": "Glasgow", "lat": 55.8642, "lon": -4.4316},
    {"name": "Bristol", "lat": 51.3827, "lon": -2.7190},
    {"name": "Liverpool John Lennon", "lat": 53.3336, "lon": -2.8497},
    {"name": "Newcastle", "lat": 55.0374, "lon": -1.6917},
    {"name": "Leeds Bradford", "lat": 53.8659, "lon": -1.6606},
    {"name": "East Midlands", "lat": 52.8311, "lon": -1.3280},
    {"name": "Belfast City", "lat": 54.6181, "lon": -5.8725},
    {"name": "Belfast International", "lat": 54.6575, "lon": -6.2158},
    {"name": "Aberdeen", "lat": 57.2019, "lon": -2.1978},
    {"name": "Southampton", "lat": 50.9503, "lon": -1.3568},
    {"name": "Cardiff", "lat": 51.3967, "lon": -3.3433},
    {"name": "Exeter", "lat": 50.7344, "lon": -3.4139},
    {"name": "Bournemouth", "lat": 50.7800, "lon": -1.8425},
    {"name": "Doncaster Sheffield", "lat": 53.4805, "lon": -1.0105},
    {"name": "Inverness", "lat": 57.5425, "lon": -4.0494},
    {"name": "Norwich", "lat": 52.6758, "lon": 1.2828},
    {"name": "Southend", "lat": 51.5714, "lon": 0.6956},
]

UK_PORTS: list[dict] = [
    {"name": "Dover", "lat": 51.1279, "lon": 1.3134},
    {"name": "Southampton", "lat": 50.8998, "lon": -1.3969},
    {"name": "Portsmouth", "lat": 50.8376, "lon": -1.0911},
    {"name": "Harwich", "lat": 51.9456, "lon": 1.2862},
    {"name": "Liverpool", "lat": 53.4488, "lon": -3.0183},
    {"name": "Hull", "lat": 53.7392, "lon": -0.2894},
    {"name": "Holyhead", "lat": 53.3094, "lon": -4.6318},
    {"name": "Fishguard", "lat": 52.0066, "lon": -4.9920},
    {"name": "Newhaven", "lat": 50.7866, "lon": 0.0603},
    {"name": "Poole", "lat": 50.7059, "lon": -1.9819},
    {"name": "Plymouth", "lat": 50.3612, "lon": -4.1372},
    {"name": "Tilbury", "lat": 51.4569, "lon": 0.3576},
    {"name": "Felixstowe", "lat": 51.9555, "lon": 1.3511},
    {"name": "Aberdeen", "lat": 57.1446, "lon": -2.0789},
    {"name": "Cairnryan", "lat": 54.9722, "lon": -5.0185},
    {"name": "Pembroke Dock", "lat": 51.6928, "lon": -4.9426},
    {"name": "Folkestone", "lat": 51.0957, "lon": 1.1765},
    {"name": "Newcastle", "lat": 55.0108, "lon": -1.4420},
    {"name": "Fleetwood", "lat": 53.9260, "lon": -3.0060},
    {"name": "Weymouth", "lat": 50.6106, "lon": -2.4549},
]

# ── Haversine math ───────────────────────────────────────────────


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometres between two lat/lon points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _build_cartesian(lats_rad: np.ndarray, lons_rad: np.ndarray) -> np.ndarray:
    """Convert lat/lon (radians) to 3D unit-sphere Cartesian for cKDTree."""
    x = np.cos(lats_rad) * np.cos(lons_rad)
    y = np.cos(lats_rad) * np.sin(lons_rad)
    z = np.sin(lats_rad)
    return np.column_stack([x, y, z])


def _point_to_cartesian(lat_deg: float, lon_deg: float) -> np.ndarray:
    """Convert a single lat/lon (degrees) to 3D unit-sphere Cartesian."""
    lat_r = math.radians(lat_deg)
    lon_r = math.radians(lon_deg)
    return np.array([
        math.cos(lat_r) * math.cos(lon_r),
        math.cos(lat_r) * math.sin(lon_r),
        math.sin(lat_r),
    ])


# ── NaPTAN data loading ─────────────────────────────────────────


def _ensure_naptan_data():
    """Download NaPTAN CSV if missing or stale, cache as parquet.

    Returns a pandas DataFrame or None on failure.
    """
    import pandas as pd

    if NAPTAN_CACHE_PATH.exists():
        age_days = (
            datetime.now(timezone.utc).timestamp()
            - os.path.getmtime(str(NAPTAN_CACHE_PATH))
        ) / 86400
        if age_days < NAPTAN_MAX_AGE_DAYS:
            try:
                return pd.read_parquet(str(NAPTAN_CACHE_PATH))
            except Exception:
                logger.warning("Failed to read cached NaPTAN parquet, re-downloading")

    logger.info("Downloading NaPTAN data (~96MB)...")
    try:
        import httpx
        resp = httpx.get(NAPTAN_CSV_URL, timeout=180, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to download NaPTAN data: %s", e)
        if NAPTAN_CACHE_PATH.exists():
            return pd.read_parquet(str(NAPTAN_CACHE_PATH))
        return None

    from io import BytesIO
    df = pd.read_csv(BytesIO(resp.content), encoding="latin-1", low_memory=False)

    keep_types = {STOP_TYPE_RAIL, STOP_TYPE_METRO, STOP_TYPE_BUS}
    df = df[df["StopType"].isin(keep_types)].copy()

    cols = ["ATCOCode", "CommonName", "Latitude", "Longitude", "StopType"]
    df = df[[c for c in cols if c in df.columns]].dropna(subset=["Latitude", "Longitude"])

    NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(NAPTAN_CACHE_PATH), index=False)
    logger.info("Cached %d NaPTAN stops to %s", len(df), NAPTAN_CACHE_PATH)
    return df


# ── KDTree singletons (lazy init) ───────────────────────────────

# Each value: (tree, original_coords_deg_array, names_list)
_trees: dict[str, tuple[cKDTree, np.ndarray, list[str]]] = {}
_airport_tree: Optional[tuple[cKDTree, list[dict]]] = None
_port_tree: Optional[tuple[cKDTree, list[dict]]] = None
_initialized = False


def _init_trees() -> bool:
    """Build cKDTrees from NaPTAN + static data. Returns True on success."""
    global _initialized, _airport_tree, _port_tree

    if _initialized:
        return bool(_trees) or _airport_tree is not None

    naptan = _ensure_naptan_data()
    if naptan is None:
        _initialized = True
        return False

    # Split by stop type (all TMU stops = "tube")
    rail = naptan[naptan["StopType"] == STOP_TYPE_RAIL]
    tube = naptan[naptan["StopType"] == STOP_TYPE_METRO]
    bus = naptan[naptan["StopType"] == STOP_TYPE_BUS]

    for key, subset in [("rail", rail), ("tube", tube), ("bus", bus)]:
        if subset.empty:
            continue
        lats = subset["Latitude"].values.astype(float)
        lons = subset["Longitude"].values.astype(float)
        cart = _build_cartesian(np.radians(lats), np.radians(lons))
        tree = cKDTree(cart)
        names = subset["CommonName"].tolist()
        _trees[key] = (tree, np.column_stack([lats, lons]), names)

    # Airports
    a_lats = np.array([a["lat"] for a in UK_AIRPORTS])
    a_lons = np.array([a["lon"] for a in UK_AIRPORTS])
    a_cart = _build_cartesian(np.radians(a_lats), np.radians(a_lons))
    _airport_tree = (cKDTree(a_cart), UK_AIRPORTS)

    # Ports
    p_lats = np.array([p["lat"] for p in UK_PORTS])
    p_lons = np.array([p["lon"] for p in UK_PORTS])
    p_cart = _build_cartesian(np.radians(p_lats), np.radians(p_lons))
    _port_tree = (cKDTree(p_cart), UK_PORTS)

    _initialized = True
    logger.info(
        "Transport trees built: %s",
        {k: len(v[2]) for k, v in _trees.items()},
    )
    return True


# ── Distance computation ─────────────────────────────────────────


def compute_transport_distances(lat: float, lon: float) -> Optional[dict]:
    """Compute all transport distances for a single lat/lon point.

    Returns dict with keys matching Property column names, or None if
    trees are unavailable.
    """
    if not _init_trees():
        return None

    point_cart = _point_to_cartesian(lat, lon)
    result: dict = {}

    # Nearest rail station
    if "rail" in _trees:
        tree, coords, names = _trees["rail"]
        _, idx = tree.query(point_cart)
        km = _haversine_km(lat, lon, float(coords[idx][0]), float(coords[idx][1]))
        result["dist_nearest_rail_km"] = round(km, 2)
        result["nearest_rail_station"] = names[idx]
    else:
        result["dist_nearest_rail_km"] = None
        result["nearest_rail_station"] = None

    # Nearest tube station
    if "tube" in _trees:
        tree, coords, names = _trees["tube"]
        _, idx = tree.query(point_cart)
        km = _haversine_km(lat, lon, float(coords[idx][0]), float(coords[idx][1]))
        result["dist_nearest_tube_km"] = round(km, 2)
        result["nearest_tube_station"] = names[idx]
    else:
        result["dist_nearest_tube_km"] = None
        result["nearest_tube_station"] = None

    # Nearest bus stop + count within 500m
    if "bus" in _trees:
        tree, coords, names = _trees["bus"]
        _, idx = tree.query(point_cart)
        km = _haversine_km(lat, lon, float(coords[idx][0]), float(coords[idx][1]))
        result["dist_nearest_bus_km"] = round(km, 2)

        # 500m in Cartesian units on unit sphere (approximate)
        radius_cart = 500.0 / (EARTH_RADIUS_KM * 1000)
        indices = tree.query_ball_point(point_cart, radius_cart)
        result["bus_stops_within_500m"] = len(indices)
    else:
        result["dist_nearest_bus_km"] = None
        result["bus_stops_within_500m"] = None

    # Nearest airport
    if _airport_tree:
        tree, airports = _airport_tree
        _, idx = tree.query(point_cart)
        km = _haversine_km(lat, lon, airports[idx]["lat"], airports[idx]["lon"])
        result["dist_nearest_airport_km"] = round(km, 2)
        result["nearest_airport"] = airports[idx]["name"]

    # Nearest port
    if _port_tree:
        tree, ports = _port_tree
        _, idx = tree.query(point_cart)
        km = _haversine_km(lat, lon, ports[idx]["lat"], ports[idx]["lon"])
        result["dist_nearest_port_km"] = round(km, 2)
        result["nearest_port"] = ports[idx]["name"]

    return result


# ── Postcode-level enrichment ────────────────────────────────────


def enrich_postcode_transport(db, postcode: str) -> dict:
    """Enrich all properties in a postcode with transport distances.

    Properties without lat/lng will be geocoded first via Postcodes.io.
    """
    from ..models import Property
    from .geocoding import geocode_postcode

    props = db.query(Property).filter(Property.postcode == postcode).all()
    if not props:
        return {
            "properties_updated": 0,
            "properties_skipped": 0,
            "message": f"No properties found for {postcode}",
        }

    # Geocode properties that lack coordinates
    needs_geo = [p for p in props if p.latitude is None or p.longitude is None]
    if needs_geo:
        coords = geocode_postcode(postcode)
        if coords:
            lat, lng = coords
            for p in needs_geo:
                p.latitude = lat
                p.longitude = lng

    updated = 0
    skipped = 0
    for prop in props:
        if prop.latitude is None or prop.longitude is None:
            skipped += 1
            continue

        distances = compute_transport_distances(prop.latitude, prop.longitude)
        if distances is None:
            skipped += 1
            continue

        for col, val in distances.items():
            setattr(prop, col, val)
        updated += 1

    if updated:
        db.commit()

    return {
        "properties_updated": updated,
        "properties_skipped": skipped,
        "message": f"Updated {updated}/{len(props)} properties with transport distances",
    }
