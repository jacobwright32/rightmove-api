"""English Indices of Multiple Deprivation (IMD) 2019 enrichment.

Looks up deprivation deciles by postcode via LSOA bridge:
  postcode → LSOA (ONS Postcode Directory) → IMD deciles (gov.uk CSV)

Downloads ~5MB CSV once, caches as parquet.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .. import config
from ..models import Property
from .ons_postcode import postcode_to_lsoa

logger = logging.getLogger(__name__)

# IMD 2019 CSV URL (gov.uk — File 7: all domains)
_IMD_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "5dc407b440f0b6379a7acc8d/File_7_-_All_IoD2019_Scores__Ranks"
    "__Deciles_and_Population_Denominators_3.csv"
)

# Column mapping: CSV column name → our field name
_DECILE_COLS = {
    "Index of Multiple Deprivation (IMD) Decile": "imd_decile",
    "Income Decile": "imd_income_decile",
    "Employment Decile": "imd_employment_decile",
    "Education, Skills and Training Decile": "imd_education_decile",
    "Health Deprivation and Disability Decile": "imd_health_decile",
    "Crime Decile": "imd_crime_decile",
    "Barriers to Housing and Services Decile": "imd_housing_decile",
    "Living Environment Decile": "imd_environment_decile",
}

_lsoa_to_deciles: Optional[dict[str, dict[str, int]]] = None
_initialized = False


def _ensure_data() -> bool:
    """Download IMD CSV if missing or stale, load into memory dict."""
    global _lsoa_to_deciles, _initialized

    if _initialized:
        return _lsoa_to_deciles is not None

    _initialized = True
    cache_path = config.IMD_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.IMD_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _load_dict(df)
                logger.info("IMD loaded from cache: %d LSOAs", len(_lsoa_to_deciles))
                return True

        # Download CSV
        import httpx

        logger.info("Downloading IMD 2019 data (~5MB)...")
        resp = httpx.get(_IMD_URL, timeout=120, follow_redirects=True)
        resp.raise_for_status()

        from io import StringIO

        df = pd.read_csv(StringIO(resp.text), encoding="latin-1")

        # Find the LSOA column
        lsoa_col = None
        for col in df.columns:
            cl = col.strip().upper()
            if "LSOA" in cl and ("CODE" in cl or "11" in cl or "21" in cl):
                lsoa_col = col
                break
        if lsoa_col is None:
            # Fallback: first column
            lsoa_col = df.columns[0]

        # Select LSOA + decile columns
        select_cols = [lsoa_col]
        rename = {lsoa_col: "lsoa"}
        for csv_col, our_col in _DECILE_COLS.items():
            # Find matching column (may have extra whitespace)
            matched = None
            for col in df.columns:
                if col.strip() == csv_col:
                    matched = col
                    break
            # Also try partial match
            if matched is None:
                for col in df.columns:
                    # e.g., "Income Decile" should match "Income Decile (where 1..."
                    if csv_col.lower() in col.lower() and "decile" in col.lower():
                        matched = col
                        break
            if matched:
                select_cols.append(matched)
                rename[matched] = our_col

        df = df[select_cols].rename(columns=rename)
        df["lsoa"] = df["lsoa"].astype(str).str.strip()

        # Convert deciles to int
        for col in _DECILE_COLS.values():
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Cache as parquet
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("IMD cached: %d LSOAs", len(df))

        _load_dict(df)
        return True

    except Exception:
        logger.exception("Failed to load IMD data")
        return False


def _load_dict(df):
    """Load LSOA→deciles dict from DataFrame."""
    global _lsoa_to_deciles
    import pandas as pd

    _lsoa_to_deciles = {}
    for _, row in df.iterrows():
        lsoa = str(row.get("lsoa", "")).strip()
        if not lsoa:
            continue
        deciles = {}
        for col in _DECILE_COLS.values():
            val = row.get(col)
            if pd.notna(val):
                deciles[col] = int(val)
        if deciles:
            _lsoa_to_deciles[lsoa] = deciles


def get_imd_for_postcode(postcode: str) -> Optional[dict[str, int]]:
    """Look up IMD deciles for a postcode.

    Returns dict of {field_name: decile_value} or None if not found.
    """
    if not _ensure_data() or _lsoa_to_deciles is None:
        return None

    lsoa = postcode_to_lsoa(postcode)
    if not lsoa:
        return None

    return _lsoa_to_deciles.get(lsoa)


def enrich_postcode_imd(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with IMD deprivation data.

    Returns dict with message, properties_updated, properties_skipped.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        return {
            "message": f"No properties for {clean}",
            "properties_updated": 0,
            "properties_skipped": 0,
        }

    deciles = get_imd_for_postcode(clean)
    if not deciles:
        return {
            "message": f"No IMD data for {clean} (LSOA not found)",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.imd_decile is not None:
            skipped += 1
            continue
        for field, value in deciles.items():
            setattr(prop, field, value)
        updated += 1

    if updated:
        db.commit()

    logger.info("IMD enrichment for %s: %d updated, %d skipped", clean, updated, skipped)
    return {
        "message": f"IMD: {updated} updated, {skipped} skipped for {clean}",
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
