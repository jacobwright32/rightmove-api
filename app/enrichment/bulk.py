"""Background bulk enrichment runner.

Optimized for speed:
- Geocoding: batch 1000 postcodes/round, 10 concurrent API calls
- Local enrichments (transport, imd, broadband, schools, healthcare,
  supermarkets, green_spaces): single bulk pass over all properties
- API enrichments (epc, flood, planning): concurrent requests, 10 at a time
- Crime: concurrent month fetching + concurrent postcodes

Usage: call start() from the API endpoint; poll status(); call stop() to cancel.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import CrimeStats, Property

logger = logging.getLogger(__name__)

# ── Enrichment types ──────────────────────────────────────────────

ALL_TYPES = [
    "geocode", "transport", "epc", "crime", "flood", "planning",
    "imd", "broadband", "schools", "healthcare", "supermarkets",
    "green_spaces", "pubs", "gyms",
]

LOCAL_TYPES = {"transport", "imd", "broadband", "schools", "healthcare", "supermarkets", "green_spaces", "pubs", "gyms"}
API_TYPES = {"epc", "crime", "flood", "planning"}


# ── Singleton state ───────────────────────────────────────────────

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_stop_flag = threading.Event()

_status: dict = {
    "running": False,
    "current_postcode": None,
    "current_type": None,
    "postcodes_done": 0,
    "postcodes_total": 0,
    "properties_enriched": 0,
    "errors": 0,
    "started_at": None,
    "finished_at": None,
    "log": [],  # last N log lines
    "types": [],
    "delay": 3.0,
}

MAX_LOG_LINES = 200


def _log(msg: str):
    """Append to in-memory log and Python logger."""
    logger.info(msg)
    _status["log"].append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {msg}")
    if len(_status["log"]) > MAX_LOG_LINES:
        _status["log"] = _status["log"][-MAX_LOG_LINES:]


# ══════════════════════════════════════════════════════════════════
# BATCH GEOCODING (Postcodes.io — free, no rate limits)
# ══════════════════════════════════════════════════════════════════


def _batch_geocode_all(db: Session):
    """1000 postcodes/round, 10 concurrent API calls of 100 each."""
    from ..enrichment.geocoding import batch_geocode_postcodes

    need_postcodes = (
        db.query(Property.postcode)
        .filter(Property.postcode.isnot(None), Property.latitude.is_(None))
        .distinct()
        .all()
    )
    pc_list = [r[0] for r in need_postcodes]

    if not pc_list:
        _log("Geocoding: all postcodes already geocoded.")
        return

    _log(f"Geocoding: {len(pc_list)} postcodes need coordinates (batch mode, 10 concurrent)")
    total_updated = 0
    round_size = 1000

    for i in range(0, len(pc_list), round_size):
        if _stop_flag.is_set():
            break

        chunk = pc_list[i:i + round_size]
        coords = batch_geocode_postcodes(chunk, concurrent=True)

        for pc, (lat, lng) in coords.items():
            updated = (
                db.query(Property)
                .filter(Property.postcode == pc, Property.latitude.is_(None))
                .update({Property.latitude: lat, Property.longitude: lng})
            )
            total_updated += updated

        if coords:
            db.commit()

        done = min(i + round_size, len(pc_list))
        _status["current_postcode"] = f"geocode batch {done}/{len(pc_list)}"
        if (done % 5000) == 0 or done == len(pc_list):
            _log(f"Geocoding: {done}/{len(pc_list)} postcodes, {total_updated} properties updated")

    _log(f"Geocoding complete: {total_updated} properties updated across {len(pc_list)} postcodes")


# ══════════════════════════════════════════════════════════════════
# BATCH LOCAL ENRICHMENTS (all in-memory computation, no API calls)
# ══════════════════════════════════════════════════════════════════


def _batch_local_enrichments(db: Session, types: list[str]):
    """Single bulk pass: load all un-enriched properties, compute everything in memory,
    batch commit every 500 rows. Replaces thousands of per-postcode DB round trips."""

    requested_local = [t for t in types if t in LOCAL_TYPES]
    if not requested_local:
        return

    # ── Init all needed data sources ──
    inits = {}
    if "transport" in requested_local:
        _log("Loading transport data (NaPTAN)...")
        from ..enrichment.transport import _init_trees as init_transport
        if init_transport():
            from ..enrichment.transport import compute_transport_distances
            inits["transport"] = compute_transport_distances
        _log("Transport data ready.")

    if "schools" in requested_local:
        _log("Loading schools data (GIAS)...")
        from ..enrichment.schools import _init_trees as init_schools
        if init_schools():
            from ..enrichment.schools import compute_school_distances
            inits["schools"] = compute_school_distances
        _log("Schools data ready.")

    if "healthcare" in requested_local:
        _log("Loading healthcare data (NHS)...")
        from ..enrichment.healthcare import _init_trees as init_healthcare
        if init_healthcare():
            from ..enrichment.healthcare import compute_healthcare_distances
            inits["healthcare"] = compute_healthcare_distances
        _log("Healthcare data ready.")

    if "supermarkets" in requested_local:
        _log("Loading supermarkets data (Geolytix)...")
        from ..enrichment.supermarkets import _init_trees as init_supermarkets
        if init_supermarkets():
            from ..enrichment.supermarkets import compute_supermarket_distances
            inits["supermarkets"] = compute_supermarket_distances
        _log("Supermarkets data ready.")

    if "green_spaces" in requested_local:
        _log("Loading green spaces data (OS)...")
        from ..enrichment.green_spaces import _init_trees as init_green
        if init_green():
            from ..enrichment.green_spaces import compute_green_space_distances
            inits["green_spaces"] = compute_green_space_distances
        _log("Green spaces data ready.")

    if "pubs" in requested_local:
        _log("Loading pubs data (OSM)...")
        from ..enrichment.pubs import _init_trees as init_pubs
        if init_pubs():
            from ..enrichment.pubs import compute_pub_distances
            inits["pubs"] = compute_pub_distances
        _log("Pubs data ready.")

    if "gyms" in requested_local:
        _log("Loading gyms data (OSM)...")
        from ..enrichment.gyms import _init_trees as init_gyms
        if init_gyms():
            from ..enrichment.gyms import compute_gym_distances
            inits["gyms"] = compute_gym_distances
        _log("Gyms data ready.")

    if "imd" in requested_local:
        _log("Loading IMD data...")
        from ..enrichment.imd import _ensure_data as init_imd, get_imd_for_postcode
        if init_imd():
            inits["imd"] = get_imd_for_postcode
        _log("IMD data ready.")

    if "broadband" in requested_local:
        _log("Loading broadband data (Ofcom)...")
        from ..enrichment.broadband import _ensure_data as init_broadband, get_broadband_for_postcode
        if init_broadband():
            inits["broadband"] = get_broadband_for_postcode
        _log("Broadband data ready.")

    if not inits:
        _log("No local enrichment data available.")
        return

    # ── Determine which columns indicate "needs enrichment" ──
    check_cols = {
        "transport": Property.dist_nearest_rail_km,
        "schools": Property.dist_nearest_primary_km,
        "healthcare": Property.dist_nearest_gp_km,
        "supermarkets": Property.dist_nearest_supermarket_km,
        "green_spaces": Property.dist_nearest_green_space_km,
        "pubs": Property.dist_nearest_pub_km,
        "gyms": Property.dist_nearest_gym_km,
        "imd": Property.imd_decile,
        "broadband": Property.broadband_median_speed,
    }

    # Types that need lat/lng vs postcode
    needs_coords = {"transport", "schools", "healthcare", "supermarkets", "green_spaces", "pubs", "gyms"}
    needs_postcode = {"imd", "broadband"}

    # ── Query properties that need at least one enrichment ──
    from sqlalchemy import or_

    active_types = [t for t in inits.keys()]
    null_filters = [check_cols[t].is_(None) for t in active_types if t in check_cols]

    if not null_filters:
        return

    query = db.query(Property).filter(or_(*null_filters))

    # Count first
    total = query.count()
    if total == 0:
        _log("Local enrichments: all properties already enriched.")
        return

    _log(f"Local enrichments: {total} properties need enrichment ({', '.join(active_types)})")
    _status["current_type"] = "local batch"

    # Process in chunks using offset to avoid re-fetching same rows
    batch_size = 500
    updated_total = 0
    processed = 0

    while True:
        if _stop_flag.is_set():
            break

        # Re-query each iteration to get fresh un-enriched properties
        props = (
            db.query(Property)
            .filter(or_(*null_filters))
            .limit(batch_size)
            .all()
        )
        if not props:
            break

        batch_updated = 0
        for prop in props:
            changed = False

            for etype, compute_fn in inits.items():
                col = check_cols.get(etype)
                if col is not None and getattr(prop, col.key) is not None:
                    continue  # Already enriched for this type

                if etype in needs_coords:
                    if prop.latitude is None or prop.longitude is None:
                        continue
                    result = compute_fn(prop.latitude, prop.longitude)
                elif etype in needs_postcode:
                    if not prop.postcode:
                        continue
                    result = compute_fn(prop.postcode)
                else:
                    continue

                if result:
                    for field, value in result.items():
                        if hasattr(prop, field):
                            setattr(prop, field, value)
                    changed = True

            if changed:
                batch_updated += 1

        db.commit()
        db.expire_all()  # Clear identity map so next query gets fresh rows

        updated_total += batch_updated
        processed += len(props)
        _status["current_postcode"] = f"local batch {processed}/{total}"

        if (processed % 5000) < batch_size or processed >= total:
            _log(f"Local enrichments: {processed}/{total} checked, {updated_total} updated")

        if len(props) < batch_size:
            break

    _log(f"Local enrichments complete: {updated_total} properties updated")


# ══════════════════════════════════════════════════════════════════
# CONCURRENT API ENRICHMENTS
# ══════════════════════════════════════════════════════════════════


def _batch_epc_all(db: Session):
    """Concurrent EPC enrichment: 10 postcodes at a time, no delay."""
    import re
    from ..config import EPC_API_EMAIL, EPC_API_KEY
    from ..enrichment.epc import fetch_epc_for_postcode

    if not EPC_API_EMAIL or not EPC_API_KEY:
        _log("EPC: no API key configured, skipping.")
        return

    # Find postcodes needing EPC
    enriched_pcs = (
        db.query(Property.postcode)
        .filter(Property.postcode.isnot(None), Property.epc_rating.isnot(None))
        .distinct()
        .subquery()
    )
    need_pcs = (
        db.query(Property.postcode)
        .filter(
            Property.postcode.isnot(None),
            ~Property.postcode.in_(db.query(enriched_pcs.c.postcode)),
        )
        .distinct()
        .all()
    )
    pc_list = [r[0] for r in need_pcs]

    if not pc_list:
        _log("EPC: all postcodes already enriched.")
        return

    _log(f"EPC: {len(pc_list)} postcodes to enrich (10 concurrent)")
    total_matched = 0

    def _fetch_epc(postcode):
        try:
            return postcode, fetch_epc_for_postcode(postcode)
        except Exception as e:
            return postcode, None

    for i in range(0, len(pc_list), 10):
        if _stop_flag.is_set():
            break

        chunk = pc_list[i:i + 10]
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(_fetch_epc, pc): pc for pc in chunk}
            for fut in as_completed(futs):
                postcode, certs = fut.result()
                if not certs:
                    continue

                epc_by_address = {}
                for cert in certs:
                    addr = cert["address"].upper().strip()
                    if addr not in epc_by_address:
                        epc_by_address[addr] = cert

                props = db.query(Property).filter(Property.postcode == postcode).all()
                for prop in props:
                    prop_addr = prop.address.upper().strip()
                    cert = epc_by_address.get(prop_addr)
                    if not cert:
                        norm = re.sub(r"[,]+", " ", prop_addr).strip()
                        norm = re.sub(r"\s+", " ", norm)
                        for epc_addr, c in epc_by_address.items():
                            epc_norm = re.sub(r"[,]+", " ", epc_addr).strip()
                            epc_norm = re.sub(r"\s+", " ", epc_norm)
                            prop_parts = norm.split()
                            epc_parts = epc_norm.split()
                            if (
                                len(prop_parts) >= 2
                                and len(epc_parts) >= 2
                                and (prop_parts[:3] == epc_parts[:3] or prop_parts[:2] == epc_parts[:2])
                            ):
                                cert = c
                                break

                    if cert and cert.get("epc_rating"):
                        prop.epc_rating = cert["epc_rating"]
                        prop.epc_score = cert.get("epc_score")
                        prop.epc_environment_impact = cert.get("environment_impact")
                        prop.estimated_energy_cost = cert.get("estimated_energy_cost")
                        total_matched += 1

        db.commit()
        done = min(i + 10, len(pc_list))
        _status["current_postcode"] = f"epc {done}/{len(pc_list)}"
        if (done % 100) == 0 or done == len(pc_list):
            _log(f"EPC: {done}/{len(pc_list)} postcodes, {total_matched} properties matched")

    _log(f"EPC complete: {total_matched} properties matched")


def _batch_flood_all(db: Session):
    """Concurrent flood risk: 10 postcodes at a time."""
    from ..enrichment.flood import get_flood_risk

    enriched_pcs = (
        db.query(Property.postcode)
        .filter(Property.postcode.isnot(None), Property.flood_risk_level.isnot(None))
        .distinct()
        .subquery()
    )
    need_pcs = (
        db.query(Property.postcode)
        .filter(
            Property.postcode.isnot(None),
            ~Property.postcode.in_(db.query(enriched_pcs.c.postcode)),
        )
        .distinct()
        .all()
    )
    pc_list = [r[0] for r in need_pcs]

    if not pc_list:
        _log("Flood: all postcodes already enriched.")
        return

    _log(f"Flood: {len(pc_list)} postcodes to check (10 concurrent)")
    total_updated = 0

    def _fetch_flood(postcode):
        try:
            return postcode, get_flood_risk(postcode)
        except Exception:
            return postcode, None

    for i in range(0, len(pc_list), 10):
        if _stop_flag.is_set():
            break

        chunk = pc_list[i:i + 10]
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {pool.submit(_fetch_flood, pc): pc for pc in chunk}
            for fut in as_completed(futs):
                postcode, result = fut.result()
                if not result or result.get("risk_level") == "unknown":
                    continue

                updated = (
                    db.query(Property)
                    .filter(Property.postcode == postcode, Property.flood_risk_level.is_(None))
                    .update({Property.flood_risk_level: result["risk_level"]})
                )
                total_updated += updated

        db.commit()
        done = min(i + 10, len(pc_list))
        _status["current_postcode"] = f"flood {done}/{len(pc_list)}"
        if (done % 100) == 0 or done == len(pc_list):
            _log(f"Flood: {done}/{len(pc_list)} postcodes, {total_updated} properties updated")

    _log(f"Flood complete: {total_updated} properties updated")


def _batch_planning_all(db: Session):
    """Concurrent planning data: 5 postcodes at a time, DB writes on main thread."""
    from ..enrichment.planning import fetch_planning_applications
    from ..enrichment.geocoding import geocode_postcode
    from ..models import PlanningApplication

    # Check which postcodes already have planning data
    try:
        cached_pcs = set(
            r[0] for r in
            db.query(PlanningApplication.postcode).distinct().all()
        )
    except Exception:
        cached_pcs = set()

    all_pcs = [
        r[0] for r in
        db.query(Property.postcode)
        .filter(Property.postcode.isnot(None))
        .distinct()
        .all()
    ]
    pc_list = [pc for pc in all_pcs if pc not in cached_pcs]

    if not pc_list:
        _log("Planning: all postcodes already have data.")
        return

    _log(f"Planning: {len(pc_list)} postcodes to fetch (5 concurrent)")
    total_apps = 0

    # Use the per-postcode fallback which handles its own DB session
    for i in range(0, len(pc_list), 5):
        if _stop_flag.is_set():
            break

        chunk = pc_list[i:i + 5]
        for pc in chunk:
            if _stop_flag.is_set():
                break
            try:
                result = _enrich_planning(db, pc, 0.0)
                if "apps_" in result:
                    total_apps += int(result.split("_")[1])
            except Exception:
                _status["errors"] += 1

        done = min(i + 5, len(pc_list))
        _status["current_postcode"] = f"planning {done}/{len(pc_list)}"
        if (done % 100) == 0 or done == len(pc_list):
            _log(f"Planning: {done}/{len(pc_list)} postcodes, {total_apps} applications")

    _log(f"Planning complete: {total_apps} applications across {len(pc_list)} postcodes")


def _batch_crime_all(db: Session):
    """Sequential crime data with no extra delay (crime.py has its own 0.125s delays)."""
    from datetime import timedelta

    # Find postcodes without recent crime data
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)

    recent_rows = (
        db.query(CrimeStats.postcode)
        .filter(CrimeStats.fetched_at >= cutoff)
        .distinct()
        .all()
    )
    recent_pcs = set(r[0] for r in recent_rows)

    all_pcs = [
        r[0] for r in
        db.query(Property.postcode)
        .filter(Property.postcode.isnot(None))
        .distinct()
        .all()
    ]
    pc_list = [pc for pc in all_pcs if pc not in recent_pcs]

    if not pc_list:
        _log("Crime: all postcodes already have recent data.")
        return

    _log(f"Crime: {len(pc_list)} postcodes to fetch (sequential, no extra delay)")
    total_crimes = 0

    for i, pc in enumerate(pc_list):
        if _stop_flag.is_set():
            break

        try:
            result = _enrich_crime(db, pc, 0.0)
            if result.startswith("crimes_"):
                total_crimes += int(result.split("_")[1])
        except Exception:
            _status["errors"] += 1

        done = i + 1
        _status["current_postcode"] = f"crime {done}/{len(pc_list)}"
        if (done % 50) == 0 or done == len(pc_list):
            _log(f"Crime: {done}/{len(pc_list)} postcodes, {total_crimes} total crimes")

    _log(f"Crime complete: {total_crimes} crimes across {len(pc_list)} postcodes")


# ══════════════════════════════════════════════════════════════════
# INDIVIDUAL FALLBACKS (kept for single-postcode API enrichment calls)
# ══════════════════════════════════════════════════════════════════


def _enrich_geocode(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.geocoding import geocode_postcode

    needs = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.latitude.is_(None))
        .count()
    )
    if needs == 0:
        return "already_geocoded"

    coords = geocode_postcode(postcode)
    if not coords:
        return "geocode_failed"

    lat, lng = coords
    updated = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.latitude.is_(None))
        .update({Property.latitude: lat, Property.longitude: lng})
    )
    db.commit()
    return f"geocoded_{updated}"


def _enrich_transport(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.transport import enrich_postcode_transport

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.dist_nearest_rail_km.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_transport(db, postcode)
    return f"updated_{result['properties_updated']}"


def _enrich_epc(db: Session, postcode: str, delay: float) -> str:
    import re
    from ..config import EPC_API_EMAIL, EPC_API_KEY
    from ..enrichment.epc import fetch_epc_for_postcode

    if not EPC_API_EMAIL or not EPC_API_KEY:
        return "no_api_key"

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.epc_rating.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    certs = fetch_epc_for_postcode(postcode)
    time.sleep(delay)
    if not certs:
        return "no_certs"

    epc_by_address = {}
    for cert in certs:
        addr = cert["address"].upper().strip()
        if addr not in epc_by_address:
            epc_by_address[addr] = cert

    props = db.query(Property).filter(Property.postcode == postcode).all()
    matched = 0
    for prop in props:
        prop_addr = prop.address.upper().strip()
        cert = epc_by_address.get(prop_addr)
        if not cert:
            norm = re.sub(r"[,]+", " ", prop_addr).strip()
            norm = re.sub(r"\s+", " ", norm)
            for epc_addr, c in epc_by_address.items():
                epc_norm = re.sub(r"[,]+", " ", epc_addr).strip()
                epc_norm = re.sub(r"\s+", " ", epc_norm)
                prop_parts = norm.split()
                epc_parts = epc_norm.split()
                if (
                    len(prop_parts) >= 2
                    and len(epc_parts) >= 2
                    and (prop_parts[:3] == epc_parts[:3] or prop_parts[:2] == epc_parts[:2])
                ):
                    cert = c
                    break

        if cert and cert.get("epc_rating"):
            prop.epc_rating = cert["epc_rating"]
            prop.epc_score = cert.get("epc_score")
            prop.epc_environment_impact = cert.get("environment_impact")
            prop.estimated_energy_cost = cert.get("estimated_energy_cost")
            matched += 1

    if matched:
        db.commit()
    return f"matched_{matched}_of_{len(certs)}"


def _enrich_crime(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.crime import get_crime_summary

    recent = (
        db.query(CrimeStats)
        .filter(CrimeStats.postcode == postcode)
        .order_by(CrimeStats.fetched_at.desc())
        .first()
    )
    if recent and recent.fetched_at:
        age = (
            datetime.now(timezone.utc)
            - recent.fetched_at.replace(tzinfo=timezone.utc)
        ).days
        if age < 30:
            return "cached"

    try:
        result = get_crime_summary(db, postcode)
        return f"crimes_{result.get('total_crimes', 0)}"
    except Exception as e:
        return f"error:{e}"


def _enrich_flood(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.flood import get_flood_risk

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.flood_risk_level.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    try:
        result = get_flood_risk(postcode)
        time.sleep(delay)
        if not result or result.get("risk_level") == "unknown":
            return "unknown"

        updated = (
            db.query(Property)
            .filter(Property.postcode == postcode, Property.flood_risk_level.is_(None))
            .update({Property.flood_risk_level: result["risk_level"]})
        )
        db.commit()
        return f"risk_{result['risk_level']}"
    except Exception as e:
        return f"error:{e}"


def _enrich_planning(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.planning import get_planning_data

    try:
        result = get_planning_data(db, postcode)
        time.sleep(delay)
        if result.get("cached"):
            return "cached"
        return f"apps_{result.get('total_count', 0)}"
    except Exception as e:
        return f"error:{e}"


def _enrich_imd(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.imd import enrich_postcode_imd

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.imd_decile.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_imd(db, postcode)
    return f"updated_{result['properties_updated']}"


def _enrich_broadband(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.broadband import enrich_postcode_broadband

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.broadband_median_speed.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_broadband(db, postcode)
    return f"updated_{result['properties_updated']}"


def _enrich_schools(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.schools import enrich_postcode_schools

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.dist_nearest_primary_km.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_schools(db, postcode)
    return f"updated_{result['properties_updated']}"


def _enrich_healthcare(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.healthcare import enrich_postcode_healthcare

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.dist_nearest_gp_km.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_healthcare(db, postcode)
    return f"updated_{result['properties_updated']}"


def _enrich_supermarkets(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.supermarkets import enrich_postcode_supermarkets

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.dist_nearest_supermarket_km.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_supermarkets(db, postcode)
    return f"updated_{result['properties_updated']}"


def _enrich_green_spaces(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.green_spaces import enrich_postcode_green_spaces

    has = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.dist_nearest_green_space_km.isnot(None))
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_green_spaces(db, postcode)
    return f"updated_{result['properties_updated']}"


_FNS = {
    "geocode": _enrich_geocode,
    "transport": _enrich_transport,
    "epc": _enrich_epc,
    "crime": _enrich_crime,
    "flood": _enrich_flood,
    "planning": _enrich_planning,
    "imd": _enrich_imd,
    "broadband": _enrich_broadband,
    "schools": _enrich_schools,
    "healthcare": _enrich_healthcare,
    "supermarkets": _enrich_supermarkets,
    "green_spaces": _enrich_green_spaces,
}

# Batch functions for types that support fast bulk processing
_BATCH_FNS = {
    "geocode": lambda db, _delay: _batch_geocode_all(db),
    "epc": lambda db, _delay: _batch_epc_all(db),
    "flood": lambda db, _delay: _batch_flood_all(db),
    "planning": lambda db, _delay: _batch_planning_all(db),
    "crime": lambda db, _delay: _batch_crime_all(db),
}


# ══════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════


def _run(types: list[str], delay: float):
    """Background thread target.

    Execution order:
    1. Batch geocoding (if requested) — concurrent API, no delay
    2. Batch local enrichments (if any requested) — single bulk pass, in-memory
    3. Batch API enrichments (if any requested) — concurrent per type
    4. Fallback per-postcode loop for any remaining types
    """
    db = SessionLocal()
    try:
        # ── Phase 1: Batch geocoding ──
        if "geocode" in types:
            _batch_geocode_all(db)
            types = [t for t in types if t != "geocode"]
            if not types:
                return

        # ── Phase 2: Batch local enrichments ──
        local_types = [t for t in types if t in LOCAL_TYPES]
        if local_types:
            _batch_local_enrichments(db, local_types)
            types = [t for t in types if t not in LOCAL_TYPES]
            if not types:
                return

        # ── Phase 3: Batch API enrichments ──
        api_batch_types = [t for t in types if t in _BATCH_FNS]
        if api_batch_types:
            for etype in api_batch_types:
                if _stop_flag.is_set():
                    break
                _status["current_type"] = etype
                _log(f"Starting batch {etype} enrichment...")
                _BATCH_FNS[etype](db, delay)
            types = [t for t in types if t not in _BATCH_FNS]
            if not types:
                return

        # ── Phase 4: Fallback per-postcode loop (for any types without batch support) ──
        if types:
            postcodes = (
                db.query(Property.postcode, func.count(Property.id).label("cnt"))
                .filter(Property.postcode.isnot(None))
                .group_by(Property.postcode)
                .order_by(func.count(Property.id).desc())
                .all()
            )
            _status["postcodes_total"] = len(postcodes)
            _log(f"Fallback loop for {len(postcodes)} postcodes, types: {types}")

            for i, (postcode, prop_count) in enumerate(postcodes):
                if _stop_flag.is_set():
                    _log("Stopped by user.")
                    break

                _status["current_postcode"] = postcode
                _status["postcodes_done"] = i

                for etype in types:
                    if _stop_flag.is_set():
                        break

                    _status["current_type"] = etype
                    fn = _FNS[etype]
                    try:
                        result = fn(db, postcode, delay)
                        if "error" in str(result):
                            _status["errors"] += 1
                            _log(f"[{i+1}/{len(postcodes)}] {postcode} {etype}: {result}")
                        elif result not in ("already_geocoded", "already_enriched", "cached", "no_api_key"):
                            _log(f"[{i+1}/{len(postcodes)}] {postcode} {etype}: {result}")
                    except Exception as e:
                        _status["errors"] += 1
                        _log(f"[{i+1}/{len(postcodes)}] {postcode} {etype} FAILED: {e}")
                        time.sleep(delay)

                _status["properties_enriched"] += prop_count
                _status["postcodes_done"] = i + 1

    except Exception as e:
        _log(f"Fatal error: {e}")
    finally:
        db.close()
        _status["running"] = False
        _status["current_postcode"] = None
        _status["current_type"] = None
        _status["finished_at"] = datetime.now(timezone.utc).isoformat()
        _log("Enrichment finished.")


# ── Public API ────────────────────────────────────────────────────


def start(types: Optional[list[str]] = None, delay: float = 3.0) -> dict:
    """Start bulk enrichment in background. Returns current status."""
    global _thread

    with _lock:
        if _status["running"]:
            return {"error": "Already running", **_status}

        use_types = types or ALL_TYPES
        invalid = [t for t in use_types if t not in _FNS]
        if invalid:
            return {"error": f"Invalid types: {invalid}"}

        _stop_flag.clear()
        _status.update({
            "running": True,
            "current_postcode": None,
            "current_type": None,
            "postcodes_done": 0,
            "postcodes_total": 0,
            "properties_enriched": 0,
            "errors": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "log": [],
            "types": use_types,
            "delay": delay,
        })

        _thread = threading.Thread(target=_run, args=(list(use_types), delay), daemon=True)
        _thread.start()

    return get_status()


def stop() -> dict:
    """Signal the background thread to stop."""
    _stop_flag.set()
    _log("Stop requested...")
    return get_status()


def get_status() -> dict:
    """Return current enrichment status."""
    return dict(_status)


def get_coverage() -> dict:
    """Return feature coverage statistics."""
    db = SessionLocal()
    try:
        total = db.query(func.count(Property.id)).scalar()

        if total == 0:
            return {"total_properties": 0, "total_postcodes": 0, "total_sales": 0, "features": []}

        from ..models import Sale

        total_postcodes = db.query(
            func.count(func.distinct(Property.postcode))
        ).filter(Property.postcode.isnot(None)).scalar()

        total_sales = db.query(func.count(Sale.id)).scalar()
        sales_with_price = db.query(func.count(Sale.id)).filter(
            Sale.price_numeric.isnot(None)
        ).scalar()

        def _count(col):
            return db.query(func.count(Property.id)).filter(col.isnot(None)).scalar()

        def _pc_count(col):
            return db.query(
                func.count(func.distinct(Property.postcode))
            ).filter(col.isnot(None)).scalar()

        crime_rows = db.query(func.count(CrimeStats.id)).scalar()
        crime_pcs = db.query(
            func.count(func.distinct(CrimeStats.postcode))
        ).scalar()

        try:
            from ..models import PlanningApplication
            planning_rows = db.query(func.count(PlanningApplication.id)).scalar()
            planning_pcs = db.query(
                func.count(func.distinct(PlanningApplication.postcode))
            ).scalar()
        except Exception:
            planning_rows = 0
            planning_pcs = 0

        features = [
            {
                "name": "Bedrooms / Bathrooms / Type",
                "filled": _count(Property.bedrooms),
                "total": total,
                "note": "From scraping",
            },
            {
                "name": "Sales (parsed price + date)",
                "filled": sales_with_price,
                "total": total_sales,
                "note": "Fully parsed",
            },
            {
                "name": "Extra Features",
                "filled": _count(Property.extra_features),
                "total": total,
                "note": "Only from slow/detail scrapes",
            },
            {
                "name": "Geocoded (lat/lng)",
                "filled": _count(Property.latitude),
                "total": total,
                "note": f"{_pc_count(Property.latitude)} postcodes",
            },
            {
                "name": "EPC Rating",
                "filled": _count(Property.epc_rating),
                "total": total,
                "note": f"{_pc_count(Property.epc_rating)} postcodes",
            },
            {
                "name": "Flood Risk",
                "filled": _count(Property.flood_risk_level),
                "total": total,
                "note": f"{_pc_count(Property.flood_risk_level)} postcodes",
            },
            {
                "name": "Transport Distances",
                "filled": _count(Property.dist_nearest_rail_km),
                "total": total,
                "note": f"{_pc_count(Property.dist_nearest_rail_km)} postcodes",
            },
            {
                "name": "Crime Data",
                "filled": crime_pcs,
                "total": total_postcodes or 1,
                "note": f"{crime_pcs} postcodes, {crime_rows} rows",
            },
            {
                "name": "Planning Applications",
                "filled": planning_pcs,
                "total": total_postcodes or 1,
                "note": f"{planning_pcs} postcodes, {planning_rows} rows",
            },
            {
                "name": "Listing Status",
                "filled": _count(Property.listing_status),
                "total": total,
                "note": f"{_pc_count(Property.listing_status)} postcodes",
            },
            {
                "name": "IMD Deprivation",
                "filled": _count(Property.imd_decile),
                "total": total,
                "note": f"{_pc_count(Property.imd_decile)} postcodes",
            },
            {
                "name": "Broadband Speed",
                "filled": _count(Property.broadband_median_speed),
                "total": total,
                "note": f"{_pc_count(Property.broadband_median_speed)} postcodes",
            },
            {
                "name": "Schools & Ofsted",
                "filled": _count(Property.dist_nearest_primary_km),
                "total": total,
                "note": f"{_pc_count(Property.dist_nearest_primary_km)} postcodes",
            },
            {
                "name": "Healthcare (GP/Hospital)",
                "filled": _count(Property.dist_nearest_gp_km),
                "total": total,
                "note": f"{_pc_count(Property.dist_nearest_gp_km)} postcodes",
            },
            {
                "name": "Supermarkets",
                "filled": _count(Property.dist_nearest_supermarket_km),
                "total": total,
                "note": f"{_pc_count(Property.dist_nearest_supermarket_km)} postcodes",
            },
            {
                "name": "Green Spaces",
                "filled": _count(Property.dist_nearest_green_space_km),
                "total": total,
                "note": f"{_pc_count(Property.dist_nearest_green_space_km)} postcodes",
            },
        ]

        return {
            "total_properties": total,
            "total_postcodes": total_postcodes,
            "total_sales": total_sales,
            "features": features,
        }
    finally:
        db.close()
