#!/usr/bin/env python3
"""Scheduled scrape — run via systemd timer or cron.

Reads scripts/scrape_config.json and scrapes configured postcodes/areas.
Designed to be run from the project root:
    python scripts/scheduled_scrape.py
"""

import json
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so `app` package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DATA_DIR, SCRAPER_FRESHNESS_DAYS
from app.database import SessionLocal
from app.routers.scraper import _is_postcode_fresh, _scrape_postcode_properties, _upsert_property
from app.scraper.rightmove import normalise_postcode_for_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("scheduled_scrape")

CONFIG_PATH = Path(__file__).resolve().parent / "scrape_config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.error("Config file not found: %s", CONFIG_PATH)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def discover_area_postcodes(partial: str) -> list:
    """Find all postcodes matching a partial outcode from local parquet files."""
    import re

    import pyarrow.parquet as pq

    partial_clean = partial.upper().replace("-", "").replace(" ", "")
    parquet_dir = DATA_DIR / "postcodes"

    outcode_match = re.match(r"([A-Z]{1,2}\d[A-Z\d]?)", partial_clean)
    if not outcode_match:
        logger.warning("Invalid area format: %s", partial)
        return []

    longest = outcode_match.group(1)
    candidates = [longest]
    if len(longest) > 2:
        shorter = re.match(r"([A-Z]{1,2}\d)", partial_clean)
        if shorter and shorter.group(1) != longest:
            candidates.append(shorter.group(1))

    for outcode in candidates:
        parquet_path = parquet_dir / f"{outcode}.parquet"
        if not parquet_path.exists():
            continue
        table = pq.read_table(parquet_path, columns=["postcode"])
        raw = table.column("postcode").to_pylist()
        matches = sorted(pc for pc in raw if pc.replace(" ", "").startswith(partial_clean))
        if matches:
            return matches

    return []


def scrape_postcode(db, postcode: str, pages: int, skip_fresh: bool) -> int:
    """Scrape a single postcode. Returns number of properties saved."""
    if skip_fresh:
        is_fresh, count = _is_postcode_fresh(db, postcode)
        if is_fresh:
            logger.info("Skipping %s (fresh, %d properties)", postcode, count)
            return 0

    pc_norm = normalise_postcode_for_url(postcode)
    try:
        properties, _ = _scrape_postcode_properties(pc_norm, pages=pages)
    except Exception as e:
        logger.error("Failed to scrape %s: %s", postcode, e)
        db.rollback()
        return 0

    saved = 0
    for prop_data in properties:
        if prop_data.address:
            _upsert_property(db, prop_data)
            saved += 1

    db.commit()
    return saved


def main():
    config = load_config()
    postcodes = config.get("postcodes", [])
    areas = config.get("areas", [])
    pages = config.get("pages", 1)
    skip_fresh = config.get("skip_fresh", True)

    # Expand areas into postcodes
    all_postcodes = list(postcodes)
    for area in areas:
        area_pcs = discover_area_postcodes(area)
        logger.info("Area %s: found %d postcodes", area, len(area_pcs))
        all_postcodes.extend(area_pcs)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for pc in all_postcodes:
        norm = pc.upper().strip()
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)

    logger.info("Starting scheduled scrape: %d postcodes, %d pages each", len(unique), pages)

    total_saved = 0
    total_skipped = 0
    total_failed = 0

    db = SessionLocal()
    try:
        for i, pc in enumerate(unique, 1):
            logger.info("[%d/%d] Scraping %s", i, len(unique), pc)
            saved = scrape_postcode(db, pc, pages, skip_fresh)
            if saved > 0:
                total_saved += saved
            elif saved == 0 and skip_fresh:
                total_skipped += 1

            # Brief pause between postcodes to be polite
            if i < len(unique):
                time.sleep(2)
    finally:
        db.close()

    logger.info(
        "Scheduled scrape complete: %d properties saved, %d postcodes skipped (fresh)",
        total_saved,
        total_skipped,
    )


if __name__ == "__main__":
    main()
