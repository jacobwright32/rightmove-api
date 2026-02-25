"""Green space proximity enrichment via OS Open Greenspace data.

Downloads the OS Open Greenspace GeoPackage (SQLite-based), parses polygon
centroids from WKB geometry, converts BNG→WGS84, builds 2 cKDTrees:
  - All green spaces
  - Parks only ("Public Park Or Garden")

5 Property columns:
  dist_nearest_park_km, nearest_park_name,
  dist_nearest_green_space_km, nearest_green_space_name,
  green_spaces_within_1km
"""

import logging
import math
import os
import sqlite3
import struct
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree
from sqlalchemy.orm import Session

from .. import config
from ..models import Property

logger = logging.getLogger(__name__)

# OS Open Greenspace — free download (GeoPackage ZIP, ~55MB)
_GREENSPACE_URL = (
    "https://api.os.uk/downloads/v1/products/OpenGreenspace/downloads"
    "?area=GB&format=GeoPackage&redirect"
)

# Earth radius in km
_R = 6371.0

# Module-level state
_all_tree: Optional[cKDTree] = None
_park_tree: Optional[cKDTree] = None
_all_data: Optional[list] = None
_park_data: Optional[list] = None
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


def _parse_wkb_polygon_centroid(wkb: bytes):
    """Extract centroid (average of exterior ring coords) from WKB polygon.

    GeoPackage standard WKB: 1-byte order, 4-byte type, then rings.
    Also handles GeoPackage binary header (GP + envelope).

    Returns (easting, northing) or None.
    """
    if wkb is None or len(wkb) < 5:
        return None

    data = bytes(wkb)

    # GeoPackage binary starts with 'GP' magic
    if data[:2] == b'GP':
        # Parse GeoPackage binary header
        # byte 0-1: magic 'GP'
        # byte 2: version
        # byte 3: flags
        flags = data[3]
        envelope_type = (flags >> 1) & 0x07
        envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
        envelope_size = envelope_sizes.get(envelope_type, 0)
        # byte 4-7: SRS ID (4 bytes)
        header_size = 8 + envelope_size
        if header_size >= len(data):
            return None
        data = data[header_size:]

    if len(data) < 5:
        return None

    # Standard WKB
    byte_order = data[0]
    fmt = '<' if byte_order == 1 else '>'

    wkb_type = struct.unpack(fmt + 'I', data[1:5])[0]
    # Type 3 = Polygon, 1003 = Polygon (with Z stripped from type)
    base_type = wkb_type % 1000
    if base_type != 3:
        # Try to handle MultiPolygon (type 6) — use first polygon
        if base_type == 6:
            if len(data) < 13:
                return None
            num_geoms = struct.unpack(fmt + 'I', data[5:9])[0]
            if num_geoms == 0:
                return None
            # Recurse into first polygon (skip multipolygon header)
            return _parse_wkb_polygon_centroid(data[9:])
        return None

    offset = 5
    if len(data) < offset + 4:
        return None

    num_rings = struct.unpack(fmt + 'I', data[offset:offset + 4])[0]
    offset += 4
    if num_rings == 0:
        return None

    # Read exterior ring
    if len(data) < offset + 4:
        return None
    num_points = struct.unpack(fmt + 'I', data[offset:offset + 4])[0]
    offset += 4

    if num_points == 0:
        return None

    # Determine coordinate dimensions (2D vs 3D)
    has_z = wkb_type > 1000 or (wkb_type & 0x80000000)
    coord_size = 24 if has_z else 16

    required = offset + num_points * coord_size
    if len(data) < required:
        # Fallback: try the other coord_size
        coord_size = 16 if has_z else 24
        has_z = not has_z
        required = offset + num_points * coord_size
        if len(data) < required:
            return None

    sum_x = 0.0
    sum_y = 0.0
    for i in range(num_points):
        pos = offset + i * coord_size
        x, y = struct.unpack(fmt + 'dd', data[pos:pos + 16])
        sum_x += x
        sum_y += y

    return sum_x / num_points, sum_y / num_points


def _init_trees() -> bool:
    """Download OS Open Greenspace data and build cKDTrees."""
    global _all_tree, _park_tree
    global _all_data, _park_data
    global _initialized

    if _initialized:
        return _all_tree is not None

    _initialized = True
    cache_path = config.GREENSPACE_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.GREENSPACE_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _build_trees(df)
                logger.info("Green spaces loaded from cache: %d sites", len(df))
                return True

        # Download ZIP from OS
        import zipfile
        from io import BytesIO

        import httpx

        from .coord_convert import bng_to_wgs84

        df = None
        try:
            logger.info("Downloading OS Open Greenspace data...")
            resp = httpx.get(_GREENSPACE_URL, timeout=600, follow_redirects=True)
            resp.raise_for_status()

            # ZIP contains a .gpkg file
            zf = zipfile.ZipFile(BytesIO(resp.content))
            gpkg_name = None
            for name in zf.namelist():
                if name.endswith(".gpkg"):
                    gpkg_name = name
                    break

            if gpkg_name is None:
                logger.error("OS Greenspace ZIP has no .gpkg file: %s", zf.namelist()[:10])
                return False

            # Extract to temp file (sqlite3 needs a file path)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
                tmp.write(zf.read(gpkg_name))
                tmp_path = tmp.name

            logger.info("Parsing GeoPackage: %s", gpkg_name)

        except Exception:
            logger.exception("Failed to download OS Open Greenspace data")
            return False

        # Read greenspace_site layer via sqlite3
        try:
            conn = sqlite3.connect(tmp_path)
            rows = conn.execute(
                "SELECT distinctive_name_1, function, geometry FROM greenspace_site"
            ).fetchall()
            conn.close()
        except Exception:
            logger.exception("Failed to read greenspace_site from GeoPackage")
            return False
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        logger.info("Read %d green space sites from GeoPackage", len(rows))

        # Parse centroids and convert BNG → WGS84
        records = []
        for name, function, geom in rows:
            centroid = _parse_wkb_polygon_centroid(geom)
            if centroid is None:
                continue

            easting, northing = centroid
            lat, lon = bng_to_wgs84(easting, northing)
            if lat is None or lon is None:
                continue

            records.append({
                "name": name or function or "Unknown",
                "function": function or "Unknown",
                "lat": lat,
                "lon": lon,
            })

        if not records:
            logger.error("No valid green space records after parsing")
            return False

        df = pd.DataFrame(records)

        # Cache
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("Green spaces cached: %d sites", len(df))

        _build_trees(df)
        return True

    except Exception:
        logger.exception("Failed to load green space data")
        return False


def _build_trees(df):
    """Build cKDTrees from the green spaces DataFrame."""
    global _all_tree, _park_tree
    global _all_data, _park_data

    def _make_tree(sub_df):
        if len(sub_df) == 0:
            return None, None
        coords = np.array([
            _to_cartesian(row["lat"], row["lon"])
            for _, row in sub_df.iterrows()
        ])
        data = [
            {"name": row["name"], "function": row["function"]}
            for _, row in sub_df.iterrows()
        ]
        return cKDTree(coords), data

    _all_tree, _all_data = _make_tree(df)

    # Parks subset
    park_mask = df["function"].str.lower() == "public park or garden"
    _park_tree, _park_data = _make_tree(df[park_mask].reset_index(drop=True))

    logger.info(
        "Green space trees built: %d all, %d parks",
        len(df),
        len(_park_data or []),
    )


def _query_nearest(tree, data, lat, lon):
    """Query cKDTree for nearest site. Returns (dist_km, name)."""
    if tree is None or data is None:
        return None, None
    point = _to_cartesian(lat, lon)
    dist, idx = tree.query(point)
    site = data[idx]
    return dist, site["name"]


def _count_within(tree, lat, lon, radius_km):
    """Count sites within radius_km."""
    if tree is None:
        return 0
    point = _to_cartesian(lat, lon)
    return len(tree.query_ball_point(point, radius_km))


def compute_green_space_distances(lat: float, lon: float) -> Optional[dict]:
    """Compute green space distances for a single property."""
    if not _init_trees():
        return None

    all_dist, all_name = _query_nearest(_all_tree, _all_data, lat, lon)
    park_dist, park_name = _query_nearest(_park_tree, _park_data, lat, lon)
    count = _count_within(_all_tree, lat, lon, 1.0)

    return {
        "dist_nearest_park_km": round(park_dist, 2) if park_dist is not None else None,
        "nearest_park_name": park_name,
        "dist_nearest_green_space_km": round(all_dist, 2) if all_dist is not None else None,
        "nearest_green_space_name": all_name,
        "green_spaces_within_1km": count,
    }


def enrich_postcode_green_spaces(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with green space distances.

    Properties need lat/lng — those without are skipped.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        return {
            "message": "No properties for %s" % clean,
            "properties_updated": 0,
            "properties_skipped": 0,
        }

    if not _init_trees():
        return {
            "message": "Green space data not available",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.dist_nearest_green_space_km is not None:
            skipped += 1
            continue
        if prop.latitude is None or prop.longitude is None:
            skipped += 1
            continue

        result = compute_green_space_distances(prop.latitude, prop.longitude)
        if result:
            for field, value in result.items():
                setattr(prop, field, value)
            updated += 1
        else:
            skipped += 1

    if updated:
        db.commit()

    logger.info(
        "Green spaces enrichment for %s: %d updated, %d skipped",
        clean, updated, skipped,
    )
    return {
        "message": "Green spaces: %d updated, %d skipped for %s" % (updated, skipped, clean),
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
