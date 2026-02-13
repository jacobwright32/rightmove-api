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
    "https://www.ofcom.org.uk/siteassets/resources/documents/"
    "research-and-data/multi-sector/infrastructure-research/"
    "connected-nations-2023/data-downloads/"
    "202305_fixed_postcode_performance_r01.zip"
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
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]

        if not csv_names:
            logger.error("Ofcom broadband ZIP has no CSV files")
            return False

        # Concatenate all area CSVs (AB, BT, CF, etc.)
        logger.info("Parsing %d CSVs from Ofcom ZIP...", len(csv_names))
        frames = []
        for csv_name in csv_names:
            with zf.open(csv_name) as f:
                frames.append(pd.read_csv(f, low_memory=False))
        df = pd.concat(frames, ignore_index=True)
        logger.info("Loaded %d rows from %d CSV files", len(df), len(csv_names))

        # Find columns — Ofcom 2023 performance data uses descriptive names
        col_lower = {c: c.lower().strip() for c in df.columns}

        pc_col = None
        median_col = None
        conn_cols = {}  # speed_threshold -> column_name
        for col, cl in col_lower.items():
            if cl in ("postcode", "pcds", "pcd"):
                pc_col = col
            elif "median" in cl and "download" in cl and "speed" in cl:
                median_col = col
            elif cl.startswith("number of connections"):
                if ">= 300" in cl:
                    conn_cols["ufbb"] = col
                elif ">= 30" in cl:
                    conn_cols["sfbb"] = col
                elif "< 2" in cl or "2<5" in cl or "5<10" in cl or "10<30" in cl or "30<300" in cl:
                    conn_cols.setdefault("_all", [])
                    conn_cols["_all"].append(col)

        if pc_col is None:
            pc_col = df.columns[0]

        # Build output DataFrame with calculated metrics
        out = pd.DataFrame()
        out["postcode"] = df[pc_col].astype(str).str.upper().str.replace(" ", "", regex=False)

        if median_col:
            out["broadband_median_speed"] = pd.to_numeric(df[median_col], errors="coerce")

        # Calculate percentages from connection counts
        all_count_cols = conn_cols.get("_all", [])
        if all_count_cols:
            for c in all_count_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            total = df[all_count_cols].sum(axis=1)
            # Also add >=300 to total if present
            if "ufbb" in conn_cols:
                df[conn_cols["ufbb"]] = pd.to_numeric(df[conn_cols["ufbb"]], errors="coerce")
                total = total + df[conn_cols["ufbb"]].fillna(0)

            if "sfbb" in conn_cols:
                df[conn_cols["sfbb"]] = pd.to_numeric(df[conn_cols["sfbb"]], errors="coerce")
                sfbb_count = df[conn_cols["sfbb"]].fillna(0)
                out["broadband_superfast_pct"] = (sfbb_count / total.replace(0, float("nan")) * 100).round(1)

            if "ufbb" in conn_cols:
                ufbb_count = df[conn_cols["ufbb"]].fillna(0)
                out["broadband_ultrafast_pct"] = (ufbb_count / total.replace(0, float("nan")) * 100).round(1)

        df = out

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
