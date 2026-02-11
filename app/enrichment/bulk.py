"""Background bulk enrichment runner.

Processes all postcodes one by one, running each enrichment type with
configurable delays between API calls to respect rate limits.

Usage: call start() from the API endpoint; poll status(); call stop() to cancel.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import CrimeStats, Property

logger = logging.getLogger(__name__)

# ── Enrichment types ──────────────────────────────────────────────

ALL_TYPES = ["geocode", "transport", "epc", "crime", "flood", "planning"]


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

MAX_LOG_LINES = 100


def _log(msg: str):
    """Append to in-memory log and Python logger."""
    logger.info(msg)
    _status["log"].append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {msg}")
    if len(_status["log"]) > MAX_LOG_LINES:
        _status["log"] = _status["log"][-MAX_LOG_LINES:]


# ── Individual enrichment functions ───────────────────────────────


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
    time.sleep(delay)
    if not coords:
        return "geocode_failed"

    lat, lng = coords
    props = (
        db.query(Property)
        .filter(Property.postcode == postcode, Property.latitude.is_(None))
        .all()
    )
    for p in props:
        p.latitude = lat
        p.longitude = lng
    db.commit()
    return f"geocoded_{len(props)}"


def _enrich_transport(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.transport import enrich_postcode_transport

    has = (
        db.query(Property)
        .filter(
            Property.postcode == postcode,
            Property.dist_nearest_rail_km.isnot(None),
        )
        .count()
    )
    if has > 0:
        return "already_enriched"

    result = enrich_postcode_transport(db, postcode)
    # No delay — transport is local computation
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

    # Reuse the same matching logic as the enrich_epc endpoint
    epc_by_address: dict[str, dict] = {}
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
            # Fuzzy: normalize and try first 2-3 words
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
        # No extra delay — crime.py has its own 0.125s delay between 60 calls
        return f"crimes_{result.get('total_crimes', 0)}"
    except Exception as e:
        return f"error:{e}"


def _enrich_flood(db: Session, postcode: str, delay: float) -> str:
    from ..enrichment.flood import get_flood_risk

    has = (
        db.query(Property)
        .filter(
            Property.postcode == postcode,
            Property.flood_risk_level.isnot(None),
        )
        .count()
    )
    if has > 0:
        return "already_enriched"

    try:
        result = get_flood_risk(postcode)
        time.sleep(delay)
        if not result or result.get("risk_level") == "unknown":
            return "unknown"

        props = db.query(Property).filter(Property.postcode == postcode).all()
        for p in props:
            p.flood_risk_level = result["risk_level"]
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


_FNS = {
    "geocode": _enrich_geocode,
    "transport": _enrich_transport,
    "epc": _enrich_epc,
    "crime": _enrich_crime,
    "flood": _enrich_flood,
    "planning": _enrich_planning,
}


# ── Main runner ───────────────────────────────────────────────────


def _run(types: list[str], delay: float):
    """Background thread target."""
    db = SessionLocal()
    try:
        # Pre-load NaPTAN if transport is selected
        if "transport" in types:
            _log("Loading NaPTAN transport data...")
            from ..enrichment.transport import _init_trees
            _init_trees()
            _log("NaPTAN ready.")

        # Get all postcodes ordered by property count desc
        postcodes = (
            db.query(Property.postcode, func.count(Property.id).label("cnt"))
            .filter(Property.postcode.isnot(None))
            .group_by(Property.postcode)
            .order_by(func.count(Property.id).desc())
            .all()
        )
        _status["postcodes_total"] = len(postcodes)
        _log(f"Starting enrichment for {len(postcodes)} postcodes, types: {types}")

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

        _thread = threading.Thread(target=_run, args=(use_types, delay), daemon=True)
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
        total = db.execute(
            func.count(Property.id).select()
        ).scalar() if False else db.query(func.count(Property.id)).scalar()

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
                "filled": crime_rows,
                "total": crime_rows or 1,  # avoid /0
                "note": f"{crime_pcs} postcodes, {crime_rows} rows",
            },
            {
                "name": "Planning Applications",
                "filled": planning_rows,
                "total": planning_rows or 1,
                "note": f"{planning_pcs} postcodes, {planning_rows} rows",
            },
            {
                "name": "Listing Status",
                "filled": _count(Property.listing_status),
                "total": total,
                "note": f"{_pc_count(Property.listing_status)} postcodes",
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
