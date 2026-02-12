"""Ofcom broadband speed enrichment.

Direct postcode → broadband metrics lookup from Ofcom Connected Nations data.
Downloads ZIP containing CSV, caches as parquet.
"""

import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from sqlalchemy.orm import Session

from .. import config
from ..models import Property

logger = logging.getLogger(__name__)

# Ofcom Connected Nations fixed broadband data (latest available)
_BROADBAND_URL = (
    "https://www.ofcom.org.uk/siteassets/research-and-data/telecoms-research/"
    "connected-nations/connected-nations-2023/fixed-postcode-2023/"
    "202305_fixed_pc_performance_r03.zip"
)

_pc_to_broadband: Optional[dict[str, dict[str, float]]] = None
_initialized = False


def _ensure_data() -> bool:
    """Download Ofcom broadband CSV if missing or stale, load into memory dict."""
    global _pc_to_broadband, _initialized

    if _initialized:
        return _pc_to_broadband is not None

    _initialized = True
    cache_path = config.BROADBAND_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.BROADBAND_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _load_dict(df)
                logger.info(
                    "Broadband loaded from cache: %d postcodes",
                    len(_pc_to_broadband),
                )
                return True

        # Download ZIP
        import zipfile

        import httpx

        logger.info("Downloading Ofcom broadband data...")
        resp = httpx.get(_BROADBAND_URL, timeout=300, follow_redirects=True)
        resp.raise_for_status()

        zf = zipfile.ZipFile(BytesIO(resp.content))
        csv_name = None
        for name in zf.namelist():
            if name.endswith(".csv"):
                csv_name = name
                break

        if csv_name is None:
            logger.error("Ofcom broadband ZIP has no CSV files")
            return False

        logger.info("Parsing %s...", csv_name)
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, low_memory=False)

        # Find columns — Ofcom uses varying names across years
        col_map = {}
        for col in df.columns:
            cl = col.lower().strip()
            if cl in ("postcode", "pcds", "pcd"):
                col_map["postcode"] = col
            elif "median" in cl and ("speed" in cl or "download" in cl):
                col_map["broadband_median_speed"] = col
            elif "superfast" in cl and ("avail" in cl or "%" in cl or "pct" in cl or "premises" in cl):
                col_map["broadband_superfast_pct"] = col
            elif "ultrafast" in cl and ("avail" in cl or "%" in cl or "pct" in cl or "premises" in cl):
                col_map["broadband_ultrafast_pct"] = col
            elif ("fttp" in cl or "full fibre" in cl or "fullfibre" in cl) and ("avail" in cl or "%" in cl or "pct" in cl or "premises" in cl):
                col_map["broadband_full_fibre_pct"] = col

        if "postcode" not in col_map:
            # Try first column as postcode
            col_map["postcode"] = df.columns[0]

        # Select and rename
        rename = {}
        select_cols = []
        for key, col in col_map.items():
            rename[col] = key
            select_cols.append(col)

        df = df[select_cols].rename(columns=rename)
        df["postcode"] = (
            df["postcode"].astype(str).str.upper().str.replace(" ", "", regex=False)
        )

        # Convert metrics to float
        for col in ["broadband_median_speed", "broadband_superfast_pct",
                     "broadband_ultrafast_pct", "broadband_full_fibre_pct"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop rows without postcode
        df = df.dropna(subset=["postcode"])

        # Cache as parquet
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("Broadband cached: %d postcodes", len(df))

        _load_dict(df)
        return True

    except Exception:
        logger.exception("Failed to load Ofcom broadband data")
        return False


def _load_dict(df):
    """Load postcode→broadband metrics dict from DataFrame."""
    global _pc_to_broadband
    import pandas as pd

    _pc_to_broadband = {}
    for _, row in df.iterrows():
        pc = str(row.get("postcode", "")).strip()
        if not pc:
            continue
        metrics = {}
        for col in ["broadband_median_speed", "broadband_superfast_pct",
                     "broadband_ultrafast_pct", "broadband_full_fibre_pct"]:
            val = row.get(col)
            if pd.notna(val):
                metrics[col] = round(float(val), 1)
        if metrics:
            _pc_to_broadband[pc] = metrics


def get_broadband_for_postcode(postcode: str) -> Optional[dict[str, float]]:
    """Look up broadband metrics for a postcode.

    Returns dict of {field_name: value} or None if not found.
    """
    if not _ensure_data() or _pc_to_broadband is None:
        return None

    norm = postcode.upper().replace(" ", "").replace("-", "")
    return _pc_to_broadband.get(norm)


def enrich_postcode_broadband(db: Session, postcode: str) -> dict:
    """Enrich all properties in a postcode with broadband speed data.

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

    metrics = get_broadband_for_postcode(clean)
    if not metrics:
        return {
            "message": f"No broadband data for {clean}",
            "properties_updated": 0,
            "properties_skipped": len(props),
        }

    updated = 0
    skipped = 0
    for prop in props:
        if prop.broadband_median_speed is not None:
            skipped += 1
            continue
        for field, value in metrics.items():
            setattr(prop, field, value)
        updated += 1

    if updated:
        db.commit()

    logger.info(
        "Broadband enrichment for %s: %d updated, %d skipped",
        clean, updated, skipped,
    )
    return {
        "message": f"Broadband: {updated} updated, {skipped} skipped for {clean}",
        "properties_updated": updated,
        "properties_skipped": skipped,
    }
