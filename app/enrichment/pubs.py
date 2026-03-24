"""Pub proximity enrichment via OpenStreetMap Overpass API.

Downloads all UK pubs from OSM, builds a cKDTree for fast spatial queries.

3 Property columns:
  dist_nearest_pub_km, nearest_pub_name, pubs_within_1km
"""

import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree
from sqlalchemy.orm import Session

from .. import config
from ..constants import OVERPASS_URL, PUBS_RADIUS_KM, OVERPASS_TIMEOUT
from ..models import Property

logger = logging.getLogger(__name__)

# Earth radius in km
_R = 6371.0

# Module-level state
_tree: Optional[cKDTree] = None
_data: Optional[list] = None
_initialized = False


def _to_cartesian(lat_deg: float, lon_deg: float):
    """Convert lat/lon degrees to 3D Cartesian for cKDTree."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    return (
        _R * math.cos(lat) * math.cos(lon),
        _R * math.cos(lat) * math.sin(lon),
        _R * math.sin(lat),
    )


def _init_trees() -> bool:
    """Download UK pub data from OSM and build cKDTree."""
    global _tree, _data, _initialized

    if _initialized:
        return _tree is not None

    _initialized = True
    cache_path = config.PUBS_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.PUBS_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _build_tree(df)
                logger.info("Pubs loaded from cache: %d pubs", len(df))
                return True

        # Download from Overpass API — all pubs in Great Britain
        import httpx

        query = """
        [out:json][timeout:300];
        area["ISO3166-1"="GB"]->.gb;
        (
          node["amenity"="pub"](area.gb);
          way["amenity"="pub"](area.gb);
          relation["amenity"="pub"](area.gb);
        );
        out center;
        """

        try:
            resp = httpx.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=OVERPASS_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("Failed to download pub data from Overpass API")
            _initialized = False  # Allow retry on next call
            return False

        # Parse elements
        records = []
        for el in data.get("elements", []):
            lat = el.get("lat") or (el.get("center", {}).get("lat"))
            lon = el.get("lon") or (el.get("center", {}).get("lon"))
            if lat is None or lon is None:
                continue
            name = el.get("tags", {}).get("name", "Unknown Pub")
            records.append({"name": name, "lat": float(lat), "lon": float(lon)})

        if not records:
            logger.error("Overpass returned no pub data")
            return False

        df = pd.DataFrame(records)

        # Cache
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("Pubs cached: %d pubs", len(df))

        _build_tree(df)
        return True

    except Exception:
        logger.exception("Failed to load pub data")
        _initialized = False  # Allow retry on next call
        return False


def _build_tree(df):
    """Build cKDTree from the pubs DataFrame."""
    global _tree, _data

    if len(df) == 0:
        return

    coords = np.array([
        _to_cartesian(row["lat"], row["lon"])
        for _, row in df.iterrows()
    ])
    _data = [{"name": row["name"]} for _, row in df.iterrows()]
    _tree = cKDTree(coords)

    logger.info("Pub tree built: %d pubs", len(df))


def _query_nearest(lat, lon):
    """Query cKDTree for nearest pub. Returns (dist_km, name)."""
    if _tree is None or _data is None:
        return None, None
    point = _to_cartesian(lat, lon)
    dist, idx = _tree.query(point)
    return dist, _data[idx]["name"]


def _count_within(lat, lon, radius_km):
    """Count pubs within radius_km."""
    if _tree is None:
        return 0
    point = _to_cartesian(lat, lon)
    return len(_tree.query_ball_point(point, radius_km))


def compute_pub_distances(lat: float, lon: float) -> Optional[dict]:
    """Compute pub distances for a single property."""
    if not _init_trees():
        return None

    dist, name = _query_nearest(lat, lon)
    count = _count_within(lat, lon, PUBS_RADIUS_KM)

    return {
        "dist_nearest_pub_km": round(dist, 2) if dist is not None else None,
        "nearest_pub_name": name,
        "pubs_within_1km": count,
    }


def enrich_postcode_pubs(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with pub distances."""
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        return {
            "message": f"No properties for {clean}",
            "properties_updated": 0,
            "properties_skipped": 0,
        }

    if not _init_trees():
        return {
            "message": "Pub data not available",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.dist_nearest_pub_km is not None:
            skipped += 1
            continue
        if prop.latitude is None or prop.longitude is None:
            skipped += 1
            continue

        result = compute_pub_distances(prop.latitude, prop.longitude)
        if result:
            for field, value in result.items():
                setattr(prop, field, value)
            updated += 1
        else:
            skipped += 1

    if updated:
        db.commit()

    logger.info(
        "Pubs enrichment for %s: %d updated, %d skipped",
        clean, updated, skipped,
    )
    return {
        "message": f"Pubs: {updated} updated, {skipped} skipped for {clean}",
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
