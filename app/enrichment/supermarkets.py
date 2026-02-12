"""Supermarket proximity enrichment via Geolytix Retail Points data.

Downloads Geolytix CSV (already has lat/lng), builds 3 cKDTrees:
  - All supermarkets
  - Premium (Waitrose, M&S Food)
  - Budget (Aldi, Lidl)

6 Property columns:
  dist_nearest_supermarket_km, nearest_supermarket_name,
  nearest_supermarket_brand, dist_nearest_premium_supermarket_km,
  dist_nearest_budget_supermarket_km, supermarkets_within_2km
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
from ..models import Property

logger = logging.getLogger(__name__)

# Geolytix Retail Points — open data supermarket locations
_GEOLYTIX_URL = (
    "https://geolytix.net/geodata/geolytix_retailpoints_v34_202312.csv"
)

# Fallback URLs if primary fails
_GEOLYTIX_FALLBACK_URLS = [
    "https://geolytix.net/geodata/geolytix_retailpoints_v33_202306.csv",
    "https://geolytix.net/geodata/geolytix_retailpoints_v32_202212.csv",
]

# Premium and budget brand classification
_PREMIUM_BRANDS = {"waitrose", "m&s food", "m&s simply food", "marks & spencer"}
_BUDGET_BRANDS = {"aldi", "lidl"}

# Major supermarket brands to include (filter out non-grocery)
_SUPERMARKET_BRANDS = {
    "tesco", "tesco express", "tesco extra", "tesco metro",
    "sainsburys", "sainsbury's", "sainsbury's local",
    "asda", "morrisons",
    "waitrose", "m&s food", "m&s simply food", "marks & spencer",
    "aldi", "lidl",
    "co-op", "cooperative", "the co-operative",
    "iceland", "farmfoods",
    "spar", "nisa", "costcutter", "budgens", "londis",
}

# Earth radius in km
_R = 6371.0

# Module-level state
_all_tree: Optional[cKDTree] = None
_premium_tree: Optional[cKDTree] = None
_budget_tree: Optional[cKDTree] = None
_all_data: Optional[list] = None
_premium_data: Optional[list] = None
_budget_data: Optional[list] = None
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
    """Download Geolytix data and build cKDTrees."""
    global _all_tree, _premium_tree, _budget_tree
    global _all_data, _premium_data, _budget_data
    global _initialized

    if _initialized:
        return _all_tree is not None

    _initialized = True
    cache_path = config.SUPERMARKETS_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.SUPERMARKETS_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _build_trees(df)
                logger.info("Supermarkets loaded from cache: %d stores", len(df))
                return True

        # Download CSV
        import httpx

        df = None
        for url in [_GEOLYTIX_URL] + _GEOLYTIX_FALLBACK_URLS:
            try:
                resp = httpx.get(url, timeout=120, follow_redirects=True)
                if resp.status_code == 200:
                    from io import StringIO
                    df = pd.read_csv(StringIO(resp.text), low_memory=False)
                    logger.info("Geolytix data downloaded from %s", url)
                    break
            except Exception:
                continue

        if df is None:
            logger.error("Failed to download Geolytix supermarket data")
            return False

        # Find relevant columns
        col_map = {}
        for col in df.columns:
            cl = col.strip().lower()
            if cl in ("retailer", "fascia", "brand", "store_name"):
                if "retailer" in cl or "fascia" in cl:
                    col_map["brand"] = col
                elif "store_name" in cl or "name" in cl:
                    col_map["name"] = col
            elif cl in ("store_name", "name") and "name" not in col_map:
                col_map["name"] = col
            elif cl in ("long_wgs", "longitude", "lon", "lng"):
                col_map["lon"] = col
            elif cl in ("lat_wgs", "latitude", "lat"):
                col_map["lat"] = col

        # Use brand as name if name not found
        if "name" not in col_map and "brand" in col_map:
            col_map["name"] = col_map["brand"]
        if "brand" not in col_map and "name" in col_map:
            col_map["brand"] = col_map["name"]

        required = ["lat", "lon"]
        for r in required:
            if r not in col_map:
                logger.error(
                    "Geolytix missing column: %s (found: %s)",
                    r, list(df.columns[:20]),
                )
                return False

        df["lat"] = pd.to_numeric(df[col_map["lat"]], errors="coerce")
        df["lon"] = pd.to_numeric(df[col_map["lon"]], errors="coerce")
        df = df.dropna(subset=["lat", "lon"])

        if "brand" in col_map:
            df["brand"] = df[col_map["brand"]].astype(str).str.strip()
        else:
            df["brand"] = "Unknown"

        if "name" in col_map and col_map["name"] != col_map.get("brand"):
            df["name"] = df[col_map["name"]].astype(str).str.strip()
        else:
            df["name"] = df["brand"]

        # Filter to known supermarket brands
        df["brand_lower"] = df["brand"].str.lower()
        mask = df["brand_lower"].apply(
            lambda b: any(known in b for known in _SUPERMARKET_BRANDS)
        )
        df = df[mask].reset_index(drop=True)
        df = df.drop(columns=["brand_lower"])

        # Keep only needed columns
        df = df[["name", "brand", "lat", "lon"]]

        # Cache
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("Supermarkets cached: %d stores", len(df))

        _build_trees(df)
        return True

    except Exception:
        logger.exception("Failed to load supermarket data")
        return False


def _build_trees(df):
    """Build cKDTrees from the supermarkets DataFrame."""
    global _all_tree, _premium_tree, _budget_tree
    global _all_data, _premium_data, _budget_data

    def _make_tree(sub_df):
        if len(sub_df) == 0:
            return None, None
        coords = np.array([
            _to_cartesian(row["lat"], row["lon"])
            for _, row in sub_df.iterrows()
        ])
        data = [
            {"name": row["name"], "brand": row["brand"]}
            for _, row in sub_df.iterrows()
        ]
        return cKDTree(coords), data

    _all_tree, _all_data = _make_tree(df)

    # Premium and budget subsets
    brand_lower = df["brand"].str.lower()
    premium_mask = brand_lower.apply(
        lambda b: any(p in b for p in _PREMIUM_BRANDS)
    )
    budget_mask = brand_lower.apply(
        lambda b: any(p in b for p in _BUDGET_BRANDS)
    )

    _premium_tree, _premium_data = _make_tree(df[premium_mask].reset_index(drop=True))
    _budget_tree, _budget_data = _make_tree(df[budget_mask].reset_index(drop=True))

    logger.info(
        "Supermarket trees built: %d all, %d premium, %d budget",
        len(df),
        len(_premium_data or []),
        len(_budget_data or []),
    )


def _query_nearest(tree, data, lat, lon):
    """Query cKDTree for nearest store. Returns (dist_km, name, brand)."""
    if tree is None or data is None:
        return None, None, None
    point = _to_cartesian(lat, lon)
    dist, idx = tree.query(point)
    store = data[idx]
    return dist, store["name"], store["brand"]


def _count_within(tree, lat, lon, radius_km):
    """Count stores within radius_km."""
    if tree is None:
        return 0
    point = _to_cartesian(lat, lon)
    return len(tree.query_ball_point(point, radius_km))


def compute_supermarket_distances(lat: float, lon: float) -> Optional[dict]:
    """Compute supermarket distances for a single property."""
    if not _init_trees():
        return None

    all_dist, all_name, all_brand = _query_nearest(_all_tree, _all_data, lat, lon)
    premium_dist, _, _ = _query_nearest(_premium_tree, _premium_data, lat, lon)
    budget_dist, _, _ = _query_nearest(_budget_tree, _budget_data, lat, lon)
    count = _count_within(_all_tree, lat, lon, 2.0)

    return {
        "dist_nearest_supermarket_km": round(all_dist, 2) if all_dist is not None else None,
        "nearest_supermarket_name": all_name,
        "nearest_supermarket_brand": all_brand,
        "dist_nearest_premium_supermarket_km": round(premium_dist, 2) if premium_dist is not None else None,
        "dist_nearest_budget_supermarket_km": round(budget_dist, 2) if budget_dist is not None else None,
        "supermarkets_within_2km": count,
    }


def enrich_postcode_supermarkets(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with supermarket distances.

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
            "message": "Supermarket data not available",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.dist_nearest_supermarket_km is not None:
            skipped += 1
            continue
        if prop.latitude is None or prop.longitude is None:
            skipped += 1
            continue

        result = compute_supermarket_distances(prop.latitude, prop.longitude)
        if result:
            for field, value in result.items():
                setattr(prop, field, value)
            updated += 1
        else:
            skipped += 1

    if updated:
        db.commit()

    logger.info(
        "Supermarkets enrichment for %s: %d updated, %d skipped",
        clean, updated, skipped,
    )
    return {
        "message": f"Supermarkets: {updated} updated, {skipped} skipped for {clean}",
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
