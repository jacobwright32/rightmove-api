"""Bulk enrichment script — slowly fills all enrichment data for every postcode.

Usage:
    python scripts/bulk_enrich.py                   # Run all enrichments
    python scripts/bulk_enrich.py --skip crime      # Skip crime (slowest)
    python scripts/bulk_enrich.py --only transport   # Only run transport
    python scripts/bulk_enrich.py --delay 5          # 5 seconds between API calls
    python scripts/bulk_enrich.py --resume           # Resume from last checkpoint

Rate: ~1000 properties/hour by default (3s delay between API calls).
Progress is saved to scripts/enrich_progress.json so you can Ctrl+C and resume.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, text

from app.database import SessionLocal, engine
from app.models import CrimeStats, Property

# ── Config ────────────────────────────────────────────────────────

PROGRESS_FILE = Path(__file__).parent / "enrich_progress.json"
DEFAULT_DELAY = 3.0  # seconds between API calls

ENRICHMENT_TYPES = ["geocode", "transport", "epc", "crime", "flood", "planning"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bulk_enrich")


# ── Progress tracking ─────────────────────────────────────────────


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"completed": {}, "started_at": None, "last_postcode": None}


def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def is_done(progress, postcode, enrichment_type):
    key = f"{postcode}:{enrichment_type}"
    return key in progress["completed"]


def mark_done(progress, postcode, enrichment_type, result="ok"):
    key = f"{postcode}:{enrichment_type}"
    progress["completed"][key] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    progress["last_postcode"] = postcode


# ── Enrichment functions ──────────────────────────────────────────


def enrich_geocode(db, postcode, delay):
    """Geocode all properties in a postcode that lack coordinates."""
    from app.enrichment.geocoding import geocode_postcode

    props = (
        db.query(Property)
        .filter(
            Property.postcode == postcode,
            Property.latitude.is_(None),
        )
        .all()
    )
    if not props:
        return "already_geocoded"

    coords = geocode_postcode(postcode)
    time.sleep(delay)

    if not coords:
        return "geocode_failed"

    lat, lng = coords
    for p in props:
        p.latitude = lat
        p.longitude = lng
    db.commit()
    return f"geocoded_{len(props)}"


def enrich_transport(db, postcode, delay):
    """Compute transport distances (local cKDTree, no API calls)."""
    from app.enrichment.transport import enrich_postcode_transport

    # Check if already enriched
    has_transport = (
        db.query(Property)
        .filter(
            Property.postcode == postcode,
            Property.dist_nearest_rail_km.isnot(None),
        )
        .count()
    )
    if has_transport > 0:
        return "already_enriched"

    result = enrich_postcode_transport(db, postcode)
    # No delay needed — transport is local computation
    return f"updated_{result['properties_updated']}"


def enrich_epc(db, postcode, delay):
    """Fetch EPC certificates and match to properties."""
    from app.config import EPC_API_EMAIL, EPC_API_KEY
    from app.enrichment.epc import fetch_epc_for_postcode

    if not EPC_API_EMAIL or not EPC_API_KEY:
        return "no_api_key"

    # Check if already enriched
    has_epc = (
        db.query(Property)
        .filter(
            Property.postcode == postcode,
            Property.epc_rating.isnot(None),
        )
        .count()
    )
    if has_epc > 0:
        return "already_enriched"

    certs = fetch_epc_for_postcode(postcode)
    time.sleep(delay)

    if not certs:
        return "no_certs_found"

    # Match certificates to properties by fuzzy address
    props = db.query(Property).filter(Property.postcode == postcode).all()
    matched = 0
    for cert in certs:
        cert_addr = cert.get("address", "").upper().strip()
        for prop in props:
            prop_addr = prop.address.upper().strip() if prop.address else ""
            # Simple substring match — EPC addresses are often shorter
            if cert_addr and prop_addr and (
                cert_addr in prop_addr or prop_addr in cert_addr
                or _fuzzy_match(cert_addr, prop_addr)
            ):
                prop.epc_rating = cert.get("epc_rating")
                prop.epc_score = cert.get("epc_score")
                prop.epc_environment_impact = cert.get("environment_impact")
                prop.estimated_energy_cost = cert.get("estimated_energy_cost")
                matched += 1
                break

    if matched:
        db.commit()
    return f"matched_{matched}_of_{len(certs)}"


def _fuzzy_match(a, b):
    """Check if addresses share a house number and street start."""
    import re
    num_a = re.match(r"(\d+)", a)
    num_b = re.match(r"(\d+)", b)
    if not num_a or not num_b:
        return False
    if num_a.group(1) != num_b.group(1):
        return False
    # Same number — check first word after number
    words_a = a[num_a.end():].strip().split()
    words_b = b[num_b.end():].strip().split()
    if words_a and words_b:
        return words_a[0] == words_b[0]
    return False


def enrich_crime(db, postcode, delay):
    """Fetch 12-month crime data from Police API."""
    from app.enrichment.crime import get_crime_summary

    # Check cache — skip if we have recent data
    recent = (
        db.query(CrimeStats)
        .filter(CrimeStats.postcode == postcode)
        .order_by(CrimeStats.fetched_at.desc())
        .first()
    )
    if recent and recent.fetched_at:
        age_days = (
            datetime.now(timezone.utc) - recent.fetched_at.replace(tzinfo=timezone.utc)
        ).days
        if age_days < 30:
            return "cached"

    try:
        result = get_crime_summary(db, postcode)
        # Crime makes ~13 API calls (1 geocode + 12 months)
        # Delay is handled per-call inside get_crime_summary... but add extra
        time.sleep(delay * 2)  # Extra delay since crime uses many calls
        return f"crimes_{result.get('total_crimes', 0)}"
    except Exception as e:
        return f"error:{e}"


def enrich_flood(db, postcode, delay):
    """Fetch flood risk data from Environment Agency."""
    # Check if already enriched
    has_flood = (
        db.query(Property)
        .filter(
            Property.postcode == postcode,
            Property.flood_risk_level.isnot(None),
        )
        .count()
    )
    if has_flood > 0:
        return "already_enriched"

    try:
        from app.enrichment.flood import get_flood_risk

        result = get_flood_risk(postcode)
        time.sleep(delay)

        if not result or result.get("risk_level") == "unknown":
            return "unknown"

        # Store on all properties in postcode
        props = db.query(Property).filter(Property.postcode == postcode).all()
        for p in props:
            p.flood_risk_level = result["risk_level"]
        db.commit()
        return f"risk_{result['risk_level']}_{len(props)}_props"
    except Exception as e:
        return f"error:{e}"


def enrich_planning(db, postcode, delay):
    """Fetch planning applications from planning.data.gov.uk."""
    try:
        from app.enrichment.planning import get_planning_data

        result = get_planning_data(db, postcode)
        time.sleep(delay)

        if result.get("cached"):
            return "cached"
        return f"apps_{result.get('total_count', 0)}"
    except Exception as e:
        return f"error:{e}"


# ── Dispatcher ────────────────────────────────────────────────────

ENRICHMENT_FNS = {
    "geocode": enrich_geocode,
    "transport": enrich_transport,
    "epc": enrich_epc,
    "crime": enrich_crime,
    "flood": enrich_flood,
    "planning": enrich_planning,
}


# ── Main ──────────────────────────────────────────────────────────


def get_all_postcodes(db):
    """Get all distinct postcodes ordered by property count (busiest first)."""
    rows = (
        db.query(Property.postcode, func.count(Property.id).label("cnt"))
        .filter(Property.postcode.isnot(None))
        .group_by(Property.postcode)
        .order_by(func.count(Property.id).desc())
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def run(args):
    progress = load_progress() if args.resume else {
        "completed": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_postcode": None,
    }

    if args.only:
        types_to_run = [t for t in args.only if t in ENRICHMENT_FNS]
    else:
        types_to_run = [t for t in ENRICHMENT_TYPES if t not in (args.skip or [])]

    db = SessionLocal()
    postcodes = get_all_postcodes(db)
    total_postcodes = len(postcodes)
    total_properties = sum(cnt for _, cnt in postcodes)

    log.info("=" * 60)
    log.info("Bulk Enrichment Script")
    log.info("=" * 60)
    log.info("Postcodes: %d  |  Properties: %d", total_postcodes, total_properties)
    log.info("Enrichments: %s", ", ".join(types_to_run))
    log.info("Delay: %.1fs between API calls", args.delay)
    log.info("Resume: %s  |  Already done: %d operations",
             args.resume, len(progress["completed"]))
    log.info("=" * 60)

    # Pre-load NaPTAN data if transport is in the list (one-time ~96MB download)
    if "transport" in types_to_run:
        log.info("Pre-loading NaPTAN transport data (first time may download ~96MB)...")
        from app.enrichment.transport import _init_trees
        _init_trees()
        log.info("NaPTAN data ready.")

    properties_enriched = 0
    api_calls = 0
    errors = 0
    start_time = time.time()

    try:
        for i, (postcode, prop_count) in enumerate(postcodes):
            elapsed = time.time() - start_time
            rate = properties_enriched / (elapsed / 3600) if elapsed > 60 else 0

            log.info(
                "[%d/%d] %s (%d props)  |  enriched: %d  |  %.0f props/hr  |  errors: %d",
                i + 1, total_postcodes, postcode, prop_count,
                properties_enriched, rate, errors,
            )

            for etype in types_to_run:
                if is_done(progress, postcode, etype):
                    continue

                fn = ENRICHMENT_FNS[etype]
                try:
                    result = fn(db, postcode, args.delay)
                    mark_done(progress, postcode, etype, result)
                    api_calls += 1

                    if "error" in str(result):
                        errors += 1
                        log.warning("  %s: %s", etype, result)
                    else:
                        log.info("  %s: %s", etype, result)

                except Exception as e:
                    errors += 1
                    mark_done(progress, postcode, etype, f"exception:{e}")
                    log.error("  %s FAILED: %s", etype, e)
                    time.sleep(args.delay)

            properties_enriched += prop_count

            # Save progress after each postcode
            if (i + 1) % 5 == 0:
                save_progress(progress)

    except KeyboardInterrupt:
        log.info("\nInterrupted! Saving progress...")
    finally:
        save_progress(progress)
        db.close()

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("Done in %.1f minutes", elapsed / 60)
    log.info("Properties enriched: %d / %d", properties_enriched, total_properties)
    log.info("API calls: %d  |  Errors: %d", api_calls, errors)
    log.info("Progress saved to %s", PROGRESS_FILE)
    log.info("Run with --resume to continue where you left off.")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk enrich all property data")
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Seconds between API calls (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--skip", nargs="+", choices=ENRICHMENT_TYPES,
        help="Enrichment types to skip",
    )
    parser.add_argument(
        "--only", nargs="+", choices=ENRICHMENT_TYPES,
        help="Only run these enrichment types",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint",
    )
    args = parser.parse_args()
    run(args)
