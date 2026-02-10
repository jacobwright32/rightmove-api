"""Merge all per-property parquet files in sales_data/ into a single file."""

import glob
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SALES_DIR = Path(__file__).resolve().parent.parent / "sales_data"
OUTPUT = SALES_DIR / "all_properties.parquet"


def main():
    pattern = str(SALES_DIR / "**" / "*.parquet")
    skip = {"all_properties.parquet", "enriched_properties.parquet"}
    files = [f for f in glob.glob(pattern, recursive=True)
             if os.path.basename(f) not in skip]
    print(f"Found {len(files)} parquet files")

    if not files:
        print("No files to merge.")
        return

    tables = []
    for f in files:
        tables.append(pq.read_table(f))

    merged = pa.concat_tables(tables, promote_options="default")
    pq.write_table(merged, OUTPUT, compression="snappy")

    size_mb = os.path.getsize(OUTPUT) / (1024 * 1024)
    print(f"Wrote {OUTPUT}")
    print(f"  Rows: {merged.num_rows}")
    print(f"  Columns: {merged.num_columns} ({', '.join(merged.column_names)})")
    print(f"  Size: {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
