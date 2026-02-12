"""ONS National Statistics Postcode Lookup (NSPL).

Provides postcode -> LSOA and postcode -> (lat, lng) lookups.
Used by IMD enrichment (LSOA bridge) and Healthcare enrichment (GP/hospital geocoding).
Downloads ~120MB CSV once, caches as ~40MB parquet.
"""

import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from .. import config

logger = logging.getLogger(__name__)

# ONS NSPL download URL (Feb 2024 release — covers all active UK postcodes)
_NSPL_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    "80592949bebd4390b2cbe29159a75ef4/data"
)

_pc_to_lsoa: Optional[dict[str, str]] = None
_pc_to_coords: Optional[dict[str, tuple[float, float]]] = None
_initialized = False


def _normalise_postcode(pc: str) -> str:
    """Normalise postcode for consistent dictionary lookup."""
    return pc.upper().replace(" ", "").replace("-", "")


def _ensure_data() -> bool:
    """Download NSPL if missing or stale, load into memory dicts."""
    global _pc_to_lsoa, _pc_to_coords, _initialized

    if _initialized:
        return _pc_to_lsoa is not None

    _initialized = True
    cache_path = config.ONS_NSPL_CACHE_PATH

    try:
        import pandas as pd

        # Check cache freshness
        if cache_path.exists():
            age_days = (
                datetime.now(timezone.utc).timestamp()
                - os.path.getmtime(str(cache_path))
            ) / 86400
            if age_days < config.ONS_NSPL_MAX_AGE_DAYS:
                df = pd.read_parquet(str(cache_path))
                _load_dicts(df)
                logger.info("ONS NSPL loaded from cache: %d postcodes", len(_pc_to_lsoa))
                return True

        # Download ZIP containing CSV
        import zipfile

        import httpx

        logger.info("Downloading ONS NSPL data (~120MB)...")
        resp = httpx.get(_NSPL_URL, timeout=300, follow_redirects=True)
        resp.raise_for_status()

        # The download is a ZIP; find the main CSV inside
        zf = zipfile.ZipFile(BytesIO(resp.content))
        csv_name = None
        for name in zf.namelist():
            if name.endswith(".csv") and "NSPL" in name.upper():
                csv_name = name
                break
        # Fallback: largest CSV in the ZIP
        if csv_name is None:
            csv_candidates = [n for n in zf.namelist() if n.endswith(".csv")]
            if csv_candidates:
                csv_name = max(csv_candidates, key=lambda n: zf.getinfo(n).file_size)

        if csv_name is None:
            logger.error("ONS NSPL ZIP has no CSV files")
            return False

        logger.info("Parsing %s...", csv_name)
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, low_memory=False, encoding="latin-1")

        # The NSPL CSV has columns: pcds (postcode), lsoa11, lat, long, doterm
        # Column names may vary slightly; find them
        col_map = {}
        for col in df.columns:
            cl = col.lower().strip()
            if cl in ("pcds", "pcd", "pcd2", "pcds2"):
                col_map["postcode"] = col
            elif cl in ("lsoa11", "lsoa11cd", "lsoa21cd", "lsoa21"):
                col_map["lsoa"] = col
            elif cl in ("lat",):
                col_map["lat"] = col
            elif cl in ("long",):
                col_map["lng"] = col
            elif cl in ("doterm",):
                col_map["doterm"] = col

        if "postcode" not in col_map:
            # Try first column as postcode
            col_map["postcode"] = df.columns[0]

        required = ["postcode"]
        for r in required:
            if r not in col_map:
                logger.error("ONS NSPL missing required column: %s (found: %s)", r, list(df.columns[:20]))
                return False

        # Select and rename
        rename = {}
        select_cols = []
        for key, col in col_map.items():
            rename[col] = key
            select_cols.append(col)

        df = df[select_cols].rename(columns=rename)

        # Filter to active postcodes (doterm is null = still active)
        if "doterm" in df.columns:
            df = df[df["doterm"].isna()].drop(columns=["doterm"])

        # Drop rows without postcode
        df = df.dropna(subset=["postcode"])

        # Normalise postcodes
        df["postcode"] = df["postcode"].astype(str).str.upper().str.replace(" ", "", regex=False)

        # Convert lat/lng to float
        if "lat" in df.columns:
            df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
        if "lng" in df.columns:
            df["lng"] = pd.to_numeric(df["lng"], errors="coerce")

        # Cache as parquet
        config.NAPTAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(str(cache_path), index=False)
        logger.info("ONS NSPL cached: %d postcodes", len(df))

        _load_dicts(df)
        return True

    except Exception:
        logger.exception("Failed to load ONS NSPL data")
        return False


def _load_dicts(df):
    """Load postcode lookup dicts from DataFrame."""
    global _pc_to_lsoa, _pc_to_coords
    import pandas as pd

    _pc_to_lsoa = {}
    _pc_to_coords = {}

    for _, row in df.iterrows():
        pc = str(row.get("postcode", ""))
        if not pc:
            continue

        lsoa = row.get("lsoa")
        if pd.notna(lsoa):
            _pc_to_lsoa[pc] = str(lsoa)

        lat = row.get("lat")
        lng = row.get("lng")
        if pd.notna(lat) and pd.notna(lng):
            _pc_to_coords[pc] = (float(lat), float(lng))


def postcode_to_lsoa(postcode: str) -> Optional[str]:
    """Look up LSOA code for a postcode. Returns None if not found."""
    if not _ensure_data() or _pc_to_lsoa is None:
        return None
    return _pc_to_lsoa.get(_normalise_postcode(postcode))


def postcode_to_coords(postcode: str) -> Optional[tuple[float, float]]:
    """Look up (lat, lng) for a postcode. Returns None if not found."""
    if not _ensure_data() or _pc_to_coords is None:
        return None
    return _pc_to_coords.get(_normalise_postcode(postcode))


def batch_postcode_to_coords(postcodes: list) -> dict[str, tuple[float, float]]:
    """Bulk look up coordinates for multiple postcodes.

    Returns dict of normalised_postcode -> (lat, lng).
    """
    if not _ensure_data() or _pc_to_coords is None:
        return {}
    result = {}
    for pc in postcodes:
        norm = _normalise_postcode(pc)
        if norm in _pc_to_coords:
            result[norm] = _pc_to_coords[norm]
    return result
