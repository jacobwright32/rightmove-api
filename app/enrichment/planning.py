"""Planning applications enrichment service.

Uses the free Planning Data API (https://www.planning.data.gov.uk/docs).
No authentication required. Geocodes postcodes via Postcodes.io.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import PlanningApplication
from .geocoding import geocode_postcode

logger = logging.getLogger(__name__)

PLANNING_API_URL = "https://www.planning.data.gov.uk/entity.json"

# Cache planning data for 30 days
PLANNING_CACHE_DAYS = 30

_DWELLING_RE = re.compile(r"(\d+)\s*(dwelling|flat|apartment|house|unit)")

# Keywords that indicate major developments
_MAJOR_KEYWORDS = [
    "demolition", "new build", "erection of", "residential development",
    "mixed use", "commercial", "industrial", "warehouse", "hotel",
    "student accommodation", "care home", "school", "hospital",
    "solar farm", "wind turbine", "infrastructure",
]


def _is_major_development(description: str) -> bool:
    """Heuristic: flag applications that look like major developments."""
    if not description:
        return False
    lower = description.lower()
    # Check for dwelling counts (e.g. "10 dwellings", "15 flats")
    dwelling_match = _DWELLING_RE.search(lower)
    if dwelling_match and int(dwelling_match.group(1)) >= 10:
        return True
    # Check keyword list
    return any(kw in lower for kw in _MAJOR_KEYWORDS)


def _parse_status(entity: dict) -> str:
    """Infer application status from entity data."""
    # The API doesn't always have explicit status; infer from dates/fields
    end_date = entity.get("end-date", "")
    decision_date = entity.get("decision-date", "")
    if end_date or decision_date:
        return "decided"
    return "pending"


def _parse_application_type(reference: str) -> str:
    """Infer application type from reference code."""
    if not reference:
        return "unknown"
    upper = reference.upper()
    if "/FUL" in upper or "/FULL" in upper:
        return "full"
    if "/OUT" in upper or "/OUTLINE" in upper:
        return "outline"
    if "/HH" in upper or "/HSE" in upper or "HOUSEHOLDER" in upper:
        return "householder"
    if "/LBC" in upper or "/LISTED" in upper:
        return "listed_building"
    if "/TPO" in upper or "/TREE" in upper:
        return "tree"
    if "/ADV" in upper or "/ADVERT" in upper:
        return "advertisement"
    if "/COU" in upper:
        return "change_of_use"
    return "other"


def fetch_planning_applications(
    lat: float,
    lng: float,
    limit: int = 50,
) -> list:
    """Fetch planning applications near coordinates from Planning Data API."""
    try:
        resp = httpx.get(
            PLANNING_API_URL,
            params={
                "latitude": lat,
                "longitude": lng,
                "dataset": "planning-application",
                "limit": min(limit, 500),
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("entities", [])
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("Planning API request failed: %s", e)
        return []
    except (ValueError, KeyError) as e:
        logger.warning("Planning API response parse error: %s", e)
        return []


def get_planning_data(
    db: Session,
    postcode: str,
    limit: int = 50,
) -> dict:
    """Get planning applications for a postcode.

    Checks cache first, then fetches from Planning Data API.
    Returns dict with applications list and metadata.
    """
    clean = postcode.upper().strip()

    # Check cache
    cached = _get_cached(db, clean)
    if cached is not None:
        return cached

    # Geocode postcode
    coords = geocode_postcode(clean)
    if not coords:
        logger.warning("Could not geocode postcode %s for planning data", clean)
        return {
            "applications": [],
            "total_count": 0,
            "major_count": 0,
            "cached": False,
        }

    lat, lng = coords

    # Fetch from API
    entities = fetch_planning_applications(lat, lng, limit)

    # Parse and store
    applications = []
    for entity in entities:
        reference = entity.get("reference", "") or str(entity.get("entity", ""))
        description = entity.get("description", "") or ""
        decision_date = entity.get("decision-date", "") or None
        app_type = _parse_application_type(reference)
        is_major = _is_major_development(description)
        status = _parse_status(entity)

        app_dict = {
            "reference": reference,
            "description": description,
            "status": status,
            "decision_date": decision_date,
            "application_type": app_type,
            "is_major": is_major,
        }
        applications.append(app_dict)

        # Cache in DB
        _cache_application(db, clean, app_dict)

    db.commit()

    major_count = sum(1 for a in applications if a["is_major"])

    return {
        "applications": applications,
        "total_count": len(applications),
        "major_count": major_count,
        "cached": False,
    }


def _get_cached(db: Session, postcode: str) -> Optional[dict]:
    """Return cached planning data if fresh enough."""
    cached_apps = (
        db.query(PlanningApplication)
        .filter(PlanningApplication.postcode == postcode)
        .all()
    )
    if not cached_apps:
        return None

    # Check freshness
    newest = max(a.fetched_at for a in cached_apps if a.fetched_at)
    if newest:
        # SQLite stores naive datetimes; ensure both are naive for comparison
        now = datetime.utcnow()
        if newest.tzinfo is not None:
            newest = newest.replace(tzinfo=None)
        age_days = (now - newest).days
        if age_days > PLANNING_CACHE_DAYS:
            # Stale — delete and re-fetch
            for a in cached_apps:
                db.delete(a)
            db.commit()
            return None

    applications = []
    for a in cached_apps:
        applications.append({
            "reference": a.reference,
            "description": a.description or "",
            "status": a.status or "pending",
            "decision_date": a.decision_date,
            "application_type": a.application_type or "other",
            "is_major": a.is_major or False,
        })

    major_count = sum(1 for a in applications if a["is_major"])

    return {
        "applications": applications,
        "total_count": len(applications),
        "major_count": major_count,
        "cached": True,
    }


def _cache_application(db: Session, postcode: str, app: dict) -> None:
    """Insert or update a planning application in the cache."""
    existing = (
        db.query(PlanningApplication)
        .filter(
            PlanningApplication.postcode == postcode,
            PlanningApplication.reference == app["reference"],
        )
        .first()
    )
    if existing:
        existing.description = app["description"]
        existing.status = app["status"]
        existing.decision_date = app.get("decision_date")
        existing.application_type = app["application_type"]
        existing.is_major = app["is_major"]
        existing.fetched_at = datetime.now(timezone.utc)
    else:
        db.add(PlanningApplication(
            postcode=postcode,
            reference=app["reference"],
            description=app["description"],
            status=app["status"],
            decision_date=app.get("decision_date"),
            application_type=app["application_type"],
            is_major=app["is_major"],
            fetched_at=datetime.now(timezone.utc),
        ))
