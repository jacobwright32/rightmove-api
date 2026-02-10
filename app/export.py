"""Shared parquet export logic for saving property sales data."""

import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .models import Property

OUTCODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)\s")
SALES_DATA_DIR = Path(__file__).resolve().parent.parent / "sales_data"


def _safe_filename(address: str) -> str:
    name = re.sub(r"[^\w\s-]", "", address).strip()
    name = re.sub(r"[\s]+", "_", name)
    return name[:200] or "unknown"


def save_property_parquet(prop: Property) -> bool:
    """Save a single property's sales to a parquet file.

    Returns True if a file was written, False if skipped.
    """
    if not prop.postcode or not prop.sales:
        return False

    m = OUTCODE_RE.match(prop.postcode.upper())
    outcode = m.group(1) if m else prop.postcode.replace(" ", "")[:4]

    out_dir = SALES_DATA_DIR / outcode
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(prop.address)
    path = out_dir / f"{filename}.parquet"

    rows = []
    for sale in prop.sales:
        rows.append({
            "address": prop.address,
            "postcode": prop.postcode,
            "property_type": sale.property_type or prop.property_type,
            "bedrooms": prop.bedrooms,
            "bathrooms": prop.bathrooms,
            "extra_features": prop.extra_features,
            "floorplan_urls": prop.floorplan_urls,
            "url": prop.url,
            "date_sold": sale.date_sold,
            "date_sold_iso": sale.date_sold_iso,
            "price": sale.price,
            "price_numeric": sale.price_numeric,
            "price_change_pct": sale.price_change_pct,
            "tenure": sale.tenure,
        })

    if not rows:
        return False

    table = pa.table({
        "address": [r["address"] for r in rows],
        "postcode": [r["postcode"] for r in rows],
        "property_type": [r["property_type"] for r in rows],
        "bedrooms": pa.array([r["bedrooms"] for r in rows], type=pa.int32()),
        "bathrooms": pa.array([r["bathrooms"] for r in rows], type=pa.int32()),
        "extra_features": [r["extra_features"] for r in rows],
        "floorplan_urls": [r["floorplan_urls"] for r in rows],
        "url": [r["url"] for r in rows],
        "date_sold": [r["date_sold"] for r in rows],
        "date_sold_iso": [r["date_sold_iso"] for r in rows],
        "price": [r["price"] for r in rows],
        "price_numeric": pa.array([r["price_numeric"] for r in rows], type=pa.int64()),
        "price_change_pct": [r["price_change_pct"] for r in rows],
        "tenure": [r["tenure"] for r in rows],
    })
    pq.write_table(table, path, compression="snappy")
    return True
