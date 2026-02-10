"""Download all UK postcodes from the ONS ArcGIS Feature Service and save as
parquet files grouped by outcode (e.g. data/postcodes/SW20.parquet).

Usage:
    python scripts/generate_postcodes.py

The ONS API returns max 2000 records per request, so we paginate using
resultOffset. Only the PCDS field (formatted postcode) is fetched.
"""

import re
import time
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests

API_URL = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Online_ONS_Postcode_Directory_Live/FeatureServer/0/query"
)
BATCH_SIZE = 2000
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "postcodes"

# Outcode is the first part of a UK postcode: "SW20 8NY" -> "SW20"
OUTCODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)\s")


def fetch_all_postcodes() -> list[str]:
    """Paginate through the ONS API and return all PCDS values."""
    postcodes: list[str] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": "PCDS",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": BATCH_SIZE,
            "resultOffset": offset,
        }
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            break

        for f in features:
            pcds = f["attributes"]["PCDS"]
            if pcds:
                postcodes.append(pcds.strip())

        print(f"  fetched {len(postcodes):,} postcodes (offset={offset})", flush=True)
        offset += BATCH_SIZE

        if not data.get("exceededTransferLimit", False):
            break

        time.sleep(0.1)  # be polite

    return postcodes


def group_by_outcode(postcodes: list[str]) -> dict[str, list[str]]:
    """Group postcodes by their outcode prefix."""
    groups: dict[str, list[str]] = defaultdict(list)
    for pc in postcodes:
        m = OUTCODE_RE.match(pc)
        if m:
            groups[m.group(1)].append(pc)
    return dict(groups)


def save_parquet_files(groups: dict[str, list[str]]) -> None:
    """Save one parquet file per outcode."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for outcode, pcs in sorted(groups.items()):
        table = pa.table({"postcode": sorted(pcs)})
        path = OUTPUT_DIR / f"{outcode}.parquet"
        pq.write_table(table, path, compression="snappy")
    print(f"  saved {len(groups)} parquet files to {OUTPUT_DIR}")


def main():
    print("Downloading all UK postcodes from ONS ArcGIS...")
    postcodes = fetch_all_postcodes()
    print(f"\nTotal postcodes: {len(postcodes):,}")

    print("Grouping by outcode...")
    groups = group_by_outcode(postcodes)
    print(f"  {len(groups)} unique outcodes")

    print("Saving parquet files...")
    save_parquet_files(groups)
    print("Done!")


if __name__ == "__main__":
    main()
