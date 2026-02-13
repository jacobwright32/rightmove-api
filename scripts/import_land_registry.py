#!/usr/bin/env python
"""Import Land Registry Price Paid Data into the rightmove-api database.

Downloads the official CSV from HM Land Registry and bulk-imports it using
raw sqlite3 for maximum performance.

Usage:
    python scripts/import_land_registry.py --mode full     # Initial full import (~30M records)
    python scripts/import_land_registry.py --mode monthly   # Incremental monthly update
    python scripts/import_land_registry.py --mode full --resume  # Resume interrupted import

Land Registry CSV (16 cols, no headers):
  0: Transaction ID (GUID)   1: Price         2: Date ("2023-01-15 00:00")
  3: Postcode                4: Type (D/S/T/F/O)  5: Old/New (Y/N)
  6: Tenure (F/L/U)          7: PAON          8: SAON
  9: Street                 10: Locality     11: Town/City
 12: District               13: County       14: PPD Category (A/B)
 15: Record Status (A/C/D)
"""

import argparse
import csv
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path so we can import app modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.address import normalise_address_key, parse_rightmove_address_key

# --- Constants ---

FULL_CSV_URL = (
    "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-complete.csv"
)
MONTHLY_CSV_URL = (
    "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-monthly-update-new-version.csv"
)

DATA_DIR = PROJECT_ROOT / "data"
FULL_CSV_PATH = DATA_DIR / "pp-complete.csv"
MONTHLY_CSV_PATH = DATA_DIR / "pp-monthly-update.csv"
CHECKPOINT_PATH = DATA_DIR / "lr_import_checkpoint.txt"

BATCH_SIZE = 50_000
CHECKPOINT_INTERVAL = 200_000

PROPERTY_TYPE_MAP = {
    "D": "DETACHED",
    "S": "SEMI-DETACHED",
    "T": "TERRACED",
    "F": "FLAT",
    "O": "OTHER",
}

TENURE_MAP = {
    "F": "FREEHOLD",
    "L": "LEASEHOLD",
    "U": "UNKNOWN",
}

MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _resolve_db_path() -> Path:
    """Resolve the SQLite database path from config or env."""
    db_url = os.getenv("DATABASE_URL", "sqlite:///./uk_house_prices.db")
    # Strip sqlite:/// prefix
    path_str = db_url.replace("sqlite:///", "")
    path = Path(path_str)
    if not path.is_absolute():
        # Relative paths are relative to CWD (matching SQLAlchemy behavior)
        path = Path.cwd() / path
    return path


def _download_csv(url: str, dest: Path) -> None:
    """Download a CSV file with progress reporting."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    print(f"  -> {dest}")

    # Use urllib for streaming download with progress
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        total = response.headers.get("Content-Length")
        total = int(total) if total else None
        downloaded = 0
        last_pct = -1

        with open(dest, "wb") as f:
            while True:
                chunk = response.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded * 100 / total)
                    if pct != last_pct:
                        print(f"\r  Progress: {pct}% ({downloaded:,} / {total:,} bytes)", end="", flush=True)
                        last_pct = pct
                else:
                    print(f"\r  Downloaded: {downloaded:,} bytes", end="", flush=True)
    print()


def _format_date_display(iso_date: str) -> str:
    """Convert '2023-01-15' to '15 Jan 2023' (no leading zero on day)."""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        day = dt.day  # No leading zero
        return f"{day} {MONTHS[dt.month]} {dt.year}"
    except (ValueError, KeyError):
        return iso_date


def _format_price_display(price: int) -> str:
    """Convert 250000 to '£250,000'."""
    return f"\u00a3{price:,}"


def _parse_csv_date(date_str: str) -> Optional[str]:
    """Parse Land Registry date '2023-01-15 00:00' to ISO '2023-01-15'."""
    if not date_str:
        return None
    return date_str[:10]  # Just take YYYY-MM-DD


def _read_checkpoint() -> int:
    """Read the last checkpoint row number, or 0 if none."""
    if CHECKPOINT_PATH.exists():
        try:
            return int(CHECKPOINT_PATH.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def _write_checkpoint(row_num: int) -> None:
    """Write a checkpoint with the current row number."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(str(row_num))


def _clear_checkpoint() -> None:
    """Remove the checkpoint file."""
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


def phase1_staging(conn: sqlite3.Connection, csv_path: Path, resume_row: int = 0) -> int:
    """Phase 1: Stream CSV into lr_staging temp table.

    Returns the total number of rows staged.
    """
    print("\n=== Phase 1: Staging CSV data ===")

    # Create staging table (drop if exists for clean start, unless resuming)
    if resume_row == 0:
        conn.execute("DROP TABLE IF EXISTS lr_staging")
        conn.execute("""
            CREATE TABLE lr_staging (
                tx_id TEXT,
                price INTEGER,
                date_sold_iso TEXT,
                date_sold TEXT,
                postcode TEXT,
                property_type TEXT,
                tenure TEXT,
                paon TEXT,
                saon TEXT,
                street TEXT,
                locality TEXT,
                town TEXT,
                address_key TEXT,
                price_display TEXT,
                record_status TEXT
            )
        """)

    total = 0
    staged = 0
    batch = []
    start = time.time()
    last_report = start

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            total += 1

            # Skip rows before checkpoint
            if total <= resume_row:
                if total % 1_000_000 == 0:
                    print(f"\r  Skipping to checkpoint... row {total:,}", end="", flush=True)
                continue

            if len(row) < 16:
                continue

            tx_id = row[0].strip('" {}')
            try:
                price = int(row[1].strip('" '))
            except (ValueError, IndexError):
                continue

            record_status = row[15].strip('" ')
            if record_status == "D":
                # Deleted record — skip
                continue

            date_iso = _parse_csv_date(row[2].strip('" '))
            if not date_iso:
                continue

            date_display = _format_date_display(date_iso)
            price_display = _format_price_display(price)
            postcode = row[3].strip('" ').upper()
            ptype_code = row[4].strip('" ').upper()
            property_type = PROPERTY_TYPE_MAP.get(ptype_code, "OTHER")
            tenure_code = row[6].strip('" ').upper()
            tenure = TENURE_MAP.get(tenure_code, "UNKNOWN")
            paon = row[7].strip('" ')
            saon = row[8].strip('" ')
            street = row[9].strip('" ')
            locality = row[10].strip('" ')
            town = row[11].strip('" ')

            if not postcode or not paon:
                continue

            address_key = normalise_address_key(paon, street, postcode, saon)

            batch.append((
                tx_id, price, date_iso, date_display, postcode,
                property_type, tenure, paon, saon, street, locality, town,
                address_key, price_display, record_status,
            ))
            staged += 1

            if len(batch) >= BATCH_SIZE:
                conn.executemany(
                    "INSERT INTO lr_staging VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                conn.commit()
                batch = []

            # Progress reporting
            now = time.time()
            if now - last_report >= 5:
                elapsed = now - start
                rate = staged / elapsed if elapsed > 0 else 0
                print(f"\r  Staged {staged:,} rows ({total:,} read) — {rate:,.0f} rows/sec", end="", flush=True)
                last_report = now

            # Checkpoint
            if total % CHECKPOINT_INTERVAL == 0:
                if batch:
                    conn.executemany(
                        "INSERT INTO lr_staging VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        batch,
                    )
                    conn.commit()
                    batch = []
                _write_checkpoint(total)

    # Flush remaining
    if batch:
        conn.executemany(
            "INSERT INTO lr_staging VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()

    elapsed = time.time() - start
    print(f"\n  Done: {staged:,} rows staged from {total:,} CSV rows in {elapsed:.1f}s")
    return staged


def phase1b_backfill_existing(conn: sqlite3.Connection) -> int:
    """Backfill address_key on existing Rightmove-sourced properties."""
    print("\n=== Phase 1b: Backfilling address_key on existing properties ===")

    cursor = conn.execute(
        "SELECT id, address FROM properties WHERE address_key IS NULL AND address IS NOT NULL"
    )
    rows = cursor.fetchall()
    if not rows:
        print("  No properties need backfilling.")
        return 0

    updates = []
    for prop_id, address in rows:
        key = parse_rightmove_address_key(address)
        if key:
            updates.append((key, prop_id))

    if updates:
        conn.executemany(
            "UPDATE properties SET address_key = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    print(f"  Backfilled {len(updates):,} of {len(rows):,} properties.")
    return len(updates)


def phase2_properties(conn: sqlite3.Connection) -> int:
    """Phase 2: Insert unique properties from staging into properties table.

    Deduplicates by address_key. Builds a full address string from LR fields.
    """
    print("\n=== Phase 2: Upserting properties ===")
    start = time.time()

    # Build address strings and insert, skipping keys that already exist
    # Address format: "SAON, PAON STREET, LOCALITY, TOWN POSTCODE"
    # (matching Rightmove-like format for display)
    conn.execute("""
        INSERT OR IGNORE INTO properties (address, postcode, property_type, address_key)
        SELECT
            CASE
                WHEN s.saon != '' THEN s.saon || ', ' || s.paon || ' ' || s.street || ', ' || s.town || ' ' || s.postcode
                ELSE s.paon || ' ' || s.street || ', ' || s.town || ' ' || s.postcode
            END,
            s.postcode,
            s.property_type,
            s.address_key
        FROM (
            SELECT paon, saon, street, town, postcode, property_type, address_key,
                   ROW_NUMBER() OVER (PARTITION BY address_key ORDER BY date_sold_iso DESC) AS rn
            FROM lr_staging
        ) s
        WHERE s.rn = 1
          AND s.address_key NOT IN (SELECT address_key FROM properties WHERE address_key IS NOT NULL)
    """)
    inserted = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()

    elapsed = time.time() - start
    print(f"  Inserted {inserted:,} new properties in {elapsed:.1f}s")
    return inserted


def phase3_sales(conn: sqlite3.Connection) -> int:
    """Phase 3: Insert sales from staging joined on address_key.

    Deduplicates by land_registry_tx_id.
    """
    print("\n=== Phase 3: Inserting sales ===")
    start = time.time()

    # Create index on staging for the join
    print("  Creating staging indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_staging_address_key ON lr_staging (address_key)")
    conn.commit()

    # Insert sales, joining staging to properties on address_key
    # Skip any tx_id that already exists
    conn.execute("""
        INSERT OR IGNORE INTO sales (
            property_id, date_sold, price, price_numeric, date_sold_iso,
            land_registry_tx_id, property_type, tenure
        )
        SELECT
            p.id,
            s.date_sold,
            s.price_display,
            s.price,
            s.date_sold_iso,
            s.tx_id,
            s.property_type,
            s.tenure
        FROM lr_staging s
        JOIN properties p ON p.address_key = s.address_key
        WHERE s.tx_id NOT IN (
            SELECT land_registry_tx_id FROM sales WHERE land_registry_tx_id IS NOT NULL
        )
    """)
    inserted = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()

    elapsed = time.time() - start
    print(f"  Inserted {inserted:,} new sales in {elapsed:.1f}s")
    return inserted


def cleanup(conn: sqlite3.Connection) -> None:
    """Drop staging table and clean up."""
    print("\n=== Cleanup ===")
    conn.execute("DROP TABLE IF EXISTS lr_staging")
    conn.commit()
    _clear_checkpoint()
    print("  Dropped lr_staging table, cleared checkpoint.")


def main():
    parser = argparse.ArgumentParser(description="Import Land Registry Price Paid Data")
    parser.add_argument(
        "--mode", choices=["full", "monthly"], default="full",
        help="full = complete dataset (~30M records), monthly = incremental update",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume interrupted staging from last checkpoint",
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to CSV file (skips download)",
    )
    parser.add_argument(
        "--keep-staging", action="store_true",
        help="Keep lr_staging table after import (for debugging)",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip download even if CSV doesn't exist",
    )
    args = parser.parse_args()

    # Resolve paths
    if args.csv:
        csv_path = Path(args.csv)
    elif args.mode == "monthly":
        csv_path = MONTHLY_CSV_PATH
    else:
        csv_path = FULL_CSV_PATH

    csv_url = MONTHLY_CSV_URL if args.mode == "monthly" else FULL_CSV_URL

    # Download if needed
    if not csv_path.exists():
        if args.skip_download:
            print(f"ERROR: CSV not found at {csv_path} and --skip-download is set.")
            sys.exit(1)
        _download_csv(csv_url, csv_path)
    else:
        size_mb = csv_path.stat().st_size / (1024 * 1024)
        print(f"Using existing CSV: {csv_path} ({size_mb:,.1f} MB)")

    # Connect to database
    db_path = _resolve_db_path()
    print(f"Database: {db_path}")
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        print("Start the FastAPI server first to create the schema, or check DATABASE_URL.")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))

    # SQLite performance optimizations
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-524288")  # 512MB
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=2147483648")  # 2GB mmap

    overall_start = time.time()

    try:
        # Check resume state
        resume_row = _read_checkpoint() if args.resume else 0
        if resume_row > 0:
            print(f"Resuming from checkpoint: row {resume_row:,}")

        # Phase 1: Stage CSV data
        staged = phase1_staging(conn, csv_path, resume_row)

        # Phase 1b: Backfill address_key on existing properties
        phase1b_backfill_existing(conn)

        # Phase 2: Upsert properties
        new_props = phase2_properties(conn)

        # Phase 3: Insert sales
        new_sales = phase3_sales(conn)

        # Cleanup
        if not args.keep_staging:
            cleanup(conn)

        # Summary
        elapsed = time.time() - overall_start
        print(f"\n{'='*60}")
        print(f"Import complete in {elapsed:.1f}s ({elapsed/60:.1f} min)")
        print(f"  Rows staged:        {staged:,}")
        print(f"  New properties:     {new_props:,}")
        print(f"  New sales:          {new_sales:,}")

        # Show totals
        prop_count = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        sale_count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        print(f"  Total properties:   {prop_count:,}")
        print(f"  Total sales:        {sale_count:,}")

        db_size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"  Database size:      {db_size_mb:,.1f} MB")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
