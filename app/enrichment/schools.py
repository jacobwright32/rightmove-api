"""Schools (GIAS) and Ofsted enrichment.

Downloads the Get Information About Schools (GIAS) CSV, converts BNG
coordinates to WGS84, builds 4 cKDTrees for nearest-neighbour lookups:
  - Primary schools (all open)
  - Secondary schools (all open)
  - Outstanding primary schools
  - Outstanding secondary schools

10 Property columns:
  dist_nearest_primary_km, dist_nearest_secondary_km,
  nearest_primary_school, nearest_secondary_school,
  nearest_primary_ofsted, nearest_secondary_ofsted,
  dist_nearest_outstanding_primary_km, dist_nearest_outstanding_secondary_km,
  primary_schools_within_2km, secondary_schools_within_3km
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree
from sqlalchemy.orm import Session

from .. import config
from ..models import Property
from .coord_convert import bng_to_wgs84

logger = logging.getLogger(__name__)

# GIAS CSV download URL — try today's date, fall back up to 7 days
_GIAS_BASE_URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/"
    "edubasealldata{date}.csv"
)

# Earth radius in km (for cKDTree conversion)
_R = 6371.0

# Module-level state
_primary_tree: Optional[cKDTree] = None
_secondary_tree: Optional[cKDTree] = None
_outstanding_primary_tree: Optional[cKDTree] = None
_outstanding_secondary_tree: Optional[cKDTree] = None

_primary_data: Optional[list] = None
_secondary_data: Optional[list] = None
_outstanding_primary_data: Optional[list] = None
_outstanding_secondary_data: Optional[list] = None

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
    """Download GIAS data, convert BNG→WGS84, build cKDTrees."""
    global _primary_tree, _secondary_tree
    global _outstanding_primary_tree, _outstanding_secondary_tree
    global _primary_data, _secondary_data
    global _outstanding_primary_data, _outstanding_secondary_data
    global _initialized

    if _initialized:
        return _primary_tree is not None

    _initialized = True
    cache_path = config.SCHOOLS_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.SCHOOLS_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _build_trees(df)
                logger.info("Schools loaded from cache: %d schools", len(df))
                return True

        # Download GIAS CSV — try today, then back up to 7 days
        import httpx

        df = None
        for days_back in range(8):
            date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
            url = _GIAS_BASE_URL.format(date=date_str)
            try:
                resp = httpx.get(url, timeout=120, follow_redirects=True)
                if resp.status_code == 200:
                    from io import StringIO
                    df = pd.read_csv(StringIO(resp.text), encoding="latin-1", low_memory=False)
                    logger.info("GIAS data downloaded for date %s", date_str)
                    break
            except Exception:
                continue

        if df is None:
            logger.error("Failed to download GIAS data (tried 8 days)")
            return False

        # Find relevant columns
        col_map = {}
        for col in df.columns:
            cl = col.strip().lower().replace(" ", "").replace("(", "").replace(")", "")
            if cl in ("urn",):
                col_map["urn"] = col
            elif cl in ("establishmentname", "schoolname", "name"):
                col_map["name"] = col
            elif cl.startswith("phaseofeducation") or cl == "phase":
                # Prefer "(name)" variant over "(code)"
                if "name" in cl or "phase" not in col_map:
                    col_map["phase"] = col
            elif "ofsted" in cl and "rating" in cl:
                if "name" in cl:
                    col_map["ofsted"] = col
                elif "ofsted" not in col_map:
                    col_map["ofsted_num"] = col
            elif cl.startswith("establishmentstatus") or cl == "status":
                # Prefer "(name)" variant
                if "name" in cl or "status" not in col_map:
                    col_map["status"] = col
            elif cl in ("easting",):
                col_map["easting"] = col
            elif cl in ("northing",):
                col_map["northing"] = col

        # Try alternative column names if not found
        if "ofsted" not in col_map:
            for col in df.columns:
                cl = col.strip().lower()
                if "ofsted" in cl and "rating" in cl:
                    col_map["ofsted"] = col
                    break

        required = ["name", "easting", "northing"]
        for r in required:
            if r not in col_map:
                logger.error("GIAS missing column: %s (found: %s)", r, list(df.columns[:30]))
                return False

        # Filter to open schools only
        if "status" in col_map:
            df = df[df[col_map["status"]].astype(str).str.lower().str.contains("open", na=False)]

        # Convert BNG to WGS84
        df["easting"] = pd.to_numeric(df[col_map["easting"]], errors="coerce")
        df["northing"] = pd.to_numeric(df[col_map["northing"]], errors="coerce")
        df = df.dropna(subset=["easting", "northing"])

        lats = []
        lons = []
        for _, row in df.iterrows():
            lat, lon = bng_to_wgs84(row["easting"], row["northing"])
            lats.append(lat)
            lons.append(lon)

        df["lat"] = lats
        df["lon"] = lons
        df = df.dropna(subset=["lat", "lon"])

        # Rename for cache
        df = df.rename(columns={col_map["name"]: "name"})
        if "phase" in col_map:
            df = df.rename(columns={col_map["phase"]: "phase"})
        if "ofsted" in col_map:
            df = df.rename(columns={col_map["ofsted"]: "ofsted"})

        # Determine phase from column
        if "phase" in df.columns:
            df["phase"] = df["phase"].astype(str).str.strip().str.lower()
        else:
            df["phase"] = "unknown"

        # Normalize Ofsted
        if "ofsted" in df.columns:
            df["ofsted"] = df["ofsted"].astype(str).str.strip()
        else:
            df["ofsted"] = ""

        # Keep only needed columns
        keep = ["name", "phase", "ofsted", "lat", "lon"]
        df = df[[c for c in keep if c in df.columns]]

        # Cache
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("Schools cached: %d schools", len(df))

        _build_trees(df)
        return True

    except Exception:
        logger.exception("Failed to load schools data")
        return False


def _build_trees(df):
    """Build cKDTrees from the schools DataFrame."""
    global _primary_tree, _secondary_tree
    global _outstanding_primary_tree, _outstanding_secondary_tree
    global _primary_data, _secondary_data
    global _outstanding_primary_data, _outstanding_secondary_data

    # Split by phase
    primary_mask = df["phase"].str.contains("primary", case=False, na=False)
    secondary_mask = df["phase"].str.contains("secondary", case=False, na=False)

    primary_df = df[primary_mask].reset_index(drop=True)
    secondary_df = df[secondary_mask].reset_index(drop=True)

    def _make_tree(sub_df):
        if len(sub_df) == 0:
            return None, None
        coords = np.array([
            _to_cartesian(row["lat"], row["lon"])
            for _, row in sub_df.iterrows()
        ])
        data = [
            {"name": row["name"], "ofsted": row.get("ofsted", ""), "lat": row["lat"], "lon": row["lon"]}
            for _, row in sub_df.iterrows()
        ]
        return cKDTree(coords), data

    _primary_tree, _primary_data = _make_tree(primary_df)
    _secondary_tree, _secondary_data = _make_tree(secondary_df)

    # Outstanding subsets
    if "ofsted" in df.columns:
        out_primary = primary_df[
            primary_df["ofsted"].str.lower().str.contains("outstanding", na=False)
        ].reset_index(drop=True)
        out_secondary = secondary_df[
            secondary_df["ofsted"].str.lower().str.contains("outstanding", na=False)
        ].reset_index(drop=True)
        _outstanding_primary_tree, _outstanding_primary_data = _make_tree(out_primary)
        _outstanding_secondary_tree, _outstanding_secondary_data = _make_tree(out_secondary)

    logger.info(
        "School trees built: %d primary, %d secondary, %d outstanding primary, %d outstanding secondary",
        len(primary_df),
        len(secondary_df),
        len(_outstanding_primary_data or []),
        len(_outstanding_secondary_data or []),
    )


def _query_nearest(tree, data, lat, lon):
    """Query cKDTree for nearest school. Returns (dist_km, name, ofsted)."""
    if tree is None or data is None:
        return None, None, None
    point = _to_cartesian(lat, lon)
    dist, idx = tree.query(point)
    school = data[idx]
    return dist, school["name"], school["ofsted"]


def _count_within(tree, lat, lon, radius_km):
    """Count how many schools within radius_km."""
    if tree is None:
        return 0
    point = _to_cartesian(lat, lon)
    return len(tree.query_ball_point(point, radius_km))


def compute_school_distances(lat: float, lon: float) -> Optional[dict]:
    """Compute school distances for a single property.

    Returns dict of property field values, or None if trees unavailable.
    """
    if not _init_trees():
        return None

    # Nearest primary
    pri_dist, pri_name, pri_ofsted = _query_nearest(_primary_tree, _primary_data, lat, lon)
    # Nearest secondary
    sec_dist, sec_name, sec_ofsted = _query_nearest(_secondary_tree, _secondary_data, lat, lon)
    # Nearest outstanding primary
    out_pri_dist, _, _ = _query_nearest(
        _outstanding_primary_tree, _outstanding_primary_data, lat, lon
    )
    # Nearest outstanding secondary
    out_sec_dist, _, _ = _query_nearest(
        _outstanding_secondary_tree, _outstanding_secondary_data, lat, lon
    )

    # Counts
    pri_count = _count_within(_primary_tree, lat, lon, 2.0)
    sec_count = _count_within(_secondary_tree, lat, lon, 3.0)

    return {
        "dist_nearest_primary_km": round(pri_dist, 2) if pri_dist is not None else None,
        "dist_nearest_secondary_km": round(sec_dist, 2) if sec_dist is not None else None,
        "nearest_primary_school": pri_name,
        "nearest_secondary_school": sec_name,
        "nearest_primary_ofsted": pri_ofsted if pri_ofsted else None,
        "nearest_secondary_ofsted": sec_ofsted if sec_ofsted else None,
        "dist_nearest_outstanding_primary_km": round(out_pri_dist, 2) if out_pri_dist is not None else None,
        "dist_nearest_outstanding_secondary_km": round(out_sec_dist, 2) if out_sec_dist is not None else None,
        "primary_schools_within_2km": pri_count,
        "secondary_schools_within_3km": sec_count,
    }


def enrich_postcode_schools(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with school distances.

    Properties need lat/lng — those without are skipped.
    """
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
            "message": "Schools data not available",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.dist_nearest_primary_km is not None:
            skipped += 1
            continue
        if prop.latitude is None or prop.longitude is None:
            skipped += 1
            continue

        result = compute_school_distances(prop.latitude, prop.longitude)
        if result:
            for field, value in result.items():
                setattr(prop, field, value)
            updated += 1
        else:
            skipped += 1

    if updated:
        db.commit()

    logger.info(
        "Schools enrichment for %s: %d updated, %d skipped",
        clean, updated, skipped,
    )
    return {
        "message": f"Schools: {updated} updated, {skipped} skipped for {clean}",
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
