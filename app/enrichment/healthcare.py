"""NHS Healthcare enrichment — GP practices and hospitals.

Downloads NHS Digital GP practice list and NHS hospital data,
geocodes via ONS Postcode Directory, builds 2 cKDTrees for nearest lookups.

5 Property columns:
  dist_nearest_gp_km, nearest_gp_name,
  dist_nearest_hospital_km, nearest_hospital_name,
  gp_practices_within_2km
"""

import logging
import math
import os
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree
from sqlalchemy.orm import Session

from .. import config
from ..models import Property
from .ons_postcode import batch_postcode_to_coords

logger = logging.getLogger(__name__)

# NHS GP practice list (epraccur.csv from NHS Digital)
_GP_URL = (
    "https://files.digital.nhs.uk/assets/ods/current/epraccur.zip"
)

# NHS hospitals — England hospital data
_HOSPITAL_URL = (
    "https://files.digital.nhs.uk/assets/ods/current/ets.zip"
)

# Earth radius in km
_R = 6371.0

# Module-level state
_gp_tree: Optional[cKDTree] = None
_hospital_tree: Optional[cKDTree] = None
_gp_data: Optional[list] = None
_hospital_data: Optional[list] = None
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
    """Download NHS data, geocode via ONS, build cKDTrees."""
    global _gp_tree, _hospital_tree, _gp_data, _hospital_data, _initialized

    if _initialized:
        return _gp_tree is not None

    _initialized = True
    cache_path = config.HEALTHCARE_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.HEALTHCARE_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _build_trees(df)
                logger.info("Healthcare loaded from cache: %d facilities", len(df))
                return True

        import zipfile

        import httpx

        # Load GP practices
        gp_records = _download_gp_practices(httpx, zipfile, pd)
        hospital_records = _download_hospitals(httpx, zipfile, pd)

        all_records = gp_records + hospital_records
        if not all_records:
            logger.error("No healthcare facilities loaded")
            return False

        df = pd.DataFrame(all_records)

        # Geocode postcodes via ONS
        postcodes = df["postcode"].dropna().unique().tolist()
        logger.info("Geocoding %d healthcare postcodes via ONS...", len(postcodes))
        coords = batch_postcode_to_coords(postcodes)

        df["postcode_norm"] = df["postcode"].str.upper().str.replace(" ", "", regex=False)
        df["lat"] = df["postcode_norm"].map(lambda pc: coords.get(pc, (None, None))[0])
        df["lon"] = df["postcode_norm"].map(lambda pc: coords.get(pc, (None, None))[1])
        df = df.dropna(subset=["lat", "lon"])
        df = df.drop(columns=["postcode_norm"])

        logger.info("Geocoded %d / %d healthcare facilities", len(df), len(all_records))

        # Cache
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)

        _build_trees(df)
        return True

    except Exception:
        logger.exception("Failed to load healthcare data")
        return False


def _download_gp_practices(httpx, zipfile, pd) -> list:
    """Download and parse NHS GP practice list."""
    records = []
    try:
        resp = httpx.get(_GP_URL, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        zf = zipfile.ZipFile(BytesIO(resp.content))

        csv_name = None
        for name in zf.namelist():
            if name.endswith(".csv"):
                csv_name = name
                break

        if csv_name is None:
            logger.warning("GP practice ZIP has no CSV files")
            return records

        with zf.open(csv_name) as f:
            # epraccur.csv is headerless fixed-width-like CSV
            content = f.read().decode("latin-1")
            df = pd.read_csv(StringIO(content), header=None, low_memory=False)

        # epraccur columns: 0=OrgCode, 1=Name, ..., 9=Postcode
        # (Column positions may vary; name is col 1, postcode is typically col 9)
        if len(df.columns) >= 10:
            for _, row in df.iterrows():
                name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
                postcode = str(row.iloc[9]).strip() if pd.notna(row.iloc[9]) else ""
                status = str(row.iloc[12]).strip() if len(df.columns) > 12 and pd.notna(row.iloc[12]) else "A"
                if name and postcode and status == "A":  # A = Active
                    records.append({"name": name, "postcode": postcode, "type": "gp"})

        logger.info("GP practices loaded: %d active", len(records))
    except Exception:
        logger.exception("Failed to download GP practices")

    return records


def _download_hospitals(httpx, zipfile, pd) -> list:
    """Download and parse NHS hospital list."""
    records = []
    try:
        resp = httpx.get(_HOSPITAL_URL, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        zf = zipfile.ZipFile(BytesIO(resp.content))

        csv_name = None
        for name in zf.namelist():
            if name.endswith(".csv"):
                csv_name = name
                break

        if csv_name is None:
            logger.warning("Hospital ZIP has no CSV files")
            return records

        with zf.open(csv_name) as f:
            content = f.read().decode("latin-1")
            df = pd.read_csv(StringIO(content), header=None, low_memory=False)

        # ets.csv columns: 0=OrgCode, 1=Name, ..., 9=Postcode
        if len(df.columns) >= 10:
            for _, row in df.iterrows():
                name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
                postcode = str(row.iloc[9]).strip() if pd.notna(row.iloc[9]) else ""
                status = str(row.iloc[12]).strip() if len(df.columns) > 12 and pd.notna(row.iloc[12]) else "A"
                if name and postcode and status == "A":
                    records.append({"name": name, "postcode": postcode, "type": "hospital"})

        logger.info("Hospitals loaded: %d active", len(records))
    except Exception:
        logger.exception("Failed to download hospitals")

    return records


def _build_trees(df):
    """Build cKDTrees from the healthcare DataFrame."""
    global _gp_tree, _hospital_tree, _gp_data, _hospital_data

    gp_df = df[df["type"] == "gp"].reset_index(drop=True)
    hospital_df = df[df["type"] == "hospital"].reset_index(drop=True)

    def _make_tree(sub_df):
        if len(sub_df) == 0:
            return None, None
        coords = np.array([
            _to_cartesian(row["lat"], row["lon"])
            for _, row in sub_df.iterrows()
        ])
        data = [
            {"name": row["name"], "lat": row["lat"], "lon": row["lon"]}
            for _, row in sub_df.iterrows()
        ]
        return cKDTree(coords), data

    _gp_tree, _gp_data = _make_tree(gp_df)
    _hospital_tree, _hospital_data = _make_tree(hospital_df)

    logger.info(
        "Healthcare trees built: %d GPs, %d hospitals",
        len(gp_df), len(hospital_df),
    )


def _query_nearest(tree, data, lat, lon):
    """Query cKDTree for nearest facility. Returns (dist_km, name)."""
    if tree is None or data is None:
        return None, None
    point = _to_cartesian(lat, lon)
    dist, idx = tree.query(point)
    return dist, data[idx]["name"]


def _count_within(tree, lat, lon, radius_km):
    """Count facilities within radius_km."""
    if tree is None:
        return 0
    point = _to_cartesian(lat, lon)
    return len(tree.query_ball_point(point, radius_km))


def compute_healthcare_distances(lat: float, lon: float) -> Optional[dict]:
    """Compute healthcare distances for a single property."""
    if not _init_trees():
        return None

    gp_dist, gp_name = _query_nearest(_gp_tree, _gp_data, lat, lon)
    hosp_dist, hosp_name = _query_nearest(_hospital_tree, _hospital_data, lat, lon)
    gp_count = _count_within(_gp_tree, lat, lon, 2.0)

    return {
        "dist_nearest_gp_km": round(gp_dist, 2) if gp_dist is not None else None,
        "nearest_gp_name": gp_name,
        "dist_nearest_hospital_km": round(hosp_dist, 2) if hosp_dist is not None else None,
        "nearest_hospital_name": hosp_name,
        "gp_practices_within_2km": gp_count,
    }


def enrich_postcode_healthcare(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with healthcare distances.

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
            "message": "Healthcare data not available",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.dist_nearest_gp_km is not None:
            skipped += 1
            continue
        if prop.latitude is None or prop.longitude is None:
            skipped += 1
            continue

        result = compute_healthcare_distances(prop.latitude, prop.longitude)
        if result:
            for field, value in result.items():
                setattr(prop, field, value)
            updated += 1
        else:
            skipped += 1

    if updated:
        db.commit()

    logger.info(
        "Healthcare enrichment for %s: %d updated, %d skipped",
        clean, updated, skipped,
    )
    return {
        "message": f"Healthcare: {updated} updated, {skipped} skipped for {clean}",
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
