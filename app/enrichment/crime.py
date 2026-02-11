"""Crime data enrichment service.

Uses the free UK Police API (no auth required): https://data.police.uk/docs/
Geocodes postcodes via Postcodes.io: https://api.postcodes.io/
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import CrimeStats
from .geocoding import geocode_postcode  # noqa: F401 — re-exported for backwards compat

logger = logging.getLogger(__name__)

POLICE_API_URL = "https://data.police.uk/api/crimes-street/all-crime"

# Cache crime data for 30 days
CRIME_CACHE_DAYS = 30


def fetch_crimes(lat: float, lng: float, date: Optional[str] = None) -> list[dict]:
    """Fetch street-level crimes from Police API.

    Args:
        lat: Latitude
        lng: Longitude
        date: Optional YYYY-MM string (defaults to latest available month)

    Returns list of crime dicts with 'category' and 'month' keys.
    """
    params = {"lat": str(lat), "lng": str(lng)}
    if date:
        params["date"] = date

    try:
        resp = httpx.get(POLICE_API_URL, params=params, timeout=15)
        if resp.status_code == 503:
            logger.warning("Police API returned 503 — data may not be available for %s", date)
            return []
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("Police API error: %s", e.response.status_code)
        return []
    except httpx.RequestError as e:
        logger.warning("Police API request failed: %s", e)
        return []


def get_crime_summary(
    db: Session, postcode: str
) -> dict:
    """Get crime summary for a postcode, using cached data if fresh.

    Returns dict with:
        - categories: {category: total_count}
        - monthly_trend: [{month, total}]
        - total_crimes: int
        - months_covered: int
        - cached: bool
    """
    clean = postcode.upper().strip()

    # Check cache
    cutoff = datetime.now(timezone.utc) - timedelta(days=CRIME_CACHE_DAYS)
    cached = (
        db.query(CrimeStats)
        .filter(CrimeStats.postcode == clean)
        .order_by(CrimeStats.fetched_at.desc())
        .first()
    )

    if cached and cached.fetched_at and cached.fetched_at.replace(tzinfo=timezone.utc) >= cutoff:
        # Serve from cache
        all_stats = (
            db.query(CrimeStats)
            .filter(CrimeStats.postcode == clean)
            .all()
        )
        return _build_summary(all_stats, cached=True)

    # Fetch fresh data
    coords = geocode_postcode(clean)
    if not coords:
        return _empty_summary()

    lat, lng = coords

    # Fetch last 12 months
    all_crimes = []
    now = datetime.now(timezone.utc)
    # Police API data lags ~2 months, try last 14 months to get 12
    for months_ago in range(2, 14):
        dt = now - timedelta(days=30 * months_ago)
        date_str = dt.strftime("%Y-%m")
        crimes = fetch_crimes(lat, lng, date_str)
        if crimes:
            all_crimes.extend(crimes)

    if not all_crimes:
        return _empty_summary()

    # Aggregate by category and month
    aggregated: dict[tuple[str, str], int] = defaultdict(int)
    for crime in all_crimes:
        cat = crime.get("category", "other")
        month = crime.get("month", "unknown")
        aggregated[(cat, month)] += 1

    # Clear old cache for this postcode and insert new
    db.query(CrimeStats).filter(CrimeStats.postcode == clean).delete()
    now_ts = datetime.now(timezone.utc)
    for (cat, month), count in aggregated.items():
        db.add(CrimeStats(
            postcode=clean,
            month=month,
            category=cat,
            count=count,
            fetched_at=now_ts,
        ))
    db.commit()

    all_stats = db.query(CrimeStats).filter(CrimeStats.postcode == clean).all()
    return _build_summary(all_stats, cached=False)


def _build_summary(stats: list[CrimeStats], cached: bool) -> dict:
    """Build summary dict from CrimeStats rows."""
    categories: dict[str, int] = defaultdict(int)
    monthly: dict[str, int] = defaultdict(int)

    for s in stats:
        categories[s.category] += s.count
        monthly[s.month] += s.count

    # Sort categories by count desc
    sorted_cats = dict(sorted(categories.items(), key=lambda x: -x[1]))
    # Sort months chronologically
    sorted_months = [
        {"month": m, "total": monthly[m]}
        for m in sorted(monthly.keys())
    ]

    total = sum(categories.values())
    return {
        "categories": sorted_cats,
        "monthly_trend": sorted_months,
        "total_crimes": total,
        "months_covered": len(sorted_months),
        "cached": cached,
    }


def _empty_summary() -> dict:
    return {
        "categories": {},
        "monthly_trend": [],
        "total_crimes": 0,
        "months_covered": 0,
        "cached": False,
    }
