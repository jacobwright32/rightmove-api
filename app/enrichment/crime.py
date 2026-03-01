"""Crime data enrichment service.

Uses the free UK Police API (no auth required): https://data.police.uk/docs/
Geocodes postcodes via Postcodes.io: https://api.postcodes.io/

Fetches 5 years of monthly crime data per postcode. Data is stored
per (postcode, month, category) in CrimeStats. The modelling pipeline
uses time-matched crime features — trailing 12-month window from sale date.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from ..constants import (
    CRIME_API_DELAY,
    CRIME_CACHE_DAYS,
    CRIME_FAILURE_THRESHOLD,
    CRIME_FETCH_MONTHS,
    CRIME_MAX_RETRIES,
    CRIME_MONTH_RE,
    CRIME_RETRY_BACKOFF,
    CRIME_TIMEOUT,
    POLICE_API_URL,
)
from ..models import CrimeStats
from .geocoding import geocode_postcode  # noqa: F401 — re-exported for backwards compat

logger = logging.getLogger(__name__)


def fetch_crimes(lat: float, lng: float, date: Optional[str] = None) -> Optional[list]:
    """Fetch street-level crimes from Police API with retry + backoff.

    Args:
        lat: Latitude
        lng: Longitude
        date: Optional YYYY-MM string (defaults to latest available month)

    Returns list of crime dicts, or None on API/network failure (distinct
    from empty list which means zero crimes for that month).
    """
    params = {"lat": str(lat), "lng": str(lng)}
    if date:
        params["date"] = date

    backoff = CRIME_RETRY_BACKOFF
    for attempt in range(CRIME_MAX_RETRIES):
        try:
            resp = httpx.get(POLICE_API_URL, params=params, timeout=CRIME_TIMEOUT)
            if resp.status_code == 503:
                # Data not yet available for this month — not a transient error
                logger.debug("Police API 503 for %s (data not available)", date)
                return []
            if resp.status_code == 429:
                logger.warning("Police API rate-limited (429), backing off %.1fs", backoff)
                time.sleep(backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Police API HTTP %s for %s (attempt %d/%d)",
                           e.response.status_code, date, attempt + 1, CRIME_MAX_RETRIES)
            if attempt < CRIME_MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            return None
        except httpx.RequestError as e:
            logger.warning("Police API request failed for %s: %s (attempt %d/%d)",
                           date, e, attempt + 1, CRIME_MAX_RETRIES)
            if attempt < CRIME_MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            return None

    return None


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

    # Fetch last 5 years of monthly data using proper month arithmetic
    all_crimes = []
    now = datetime.now(timezone.utc)
    api_failures = 0

    # Police API data lags ~2 months, fetch from month -2 to -(CRIME_FETCH_MONTHS+1)
    for months_ago in range(2, CRIME_FETCH_MONTHS + 2):
        dt = now - relativedelta(months=months_ago)
        date_str = dt.strftime("%Y-%m")
        crimes = fetch_crimes(lat, lng, date_str)
        if crimes is None:
            # API/network failure — don't count as "zero crimes"
            api_failures += 1
        elif crimes:
            all_crimes.extend(crimes)
        time.sleep(CRIME_API_DELAY)

    # If >50% of months had API failures, don't cache — data is unreliable
    if api_failures > CRIME_FETCH_MONTHS * CRIME_FAILURE_THRESHOLD:
        logger.warning(
            "Crime fetch for %s: %d/%d months had API failures, not caching",
            clean, api_failures, CRIME_FETCH_MONTHS,
        )
        if not all_crimes:
            return _empty_summary()
        # Return what we have without caching
        return _build_summary_from_crimes(all_crimes, cached=False)

    if not all_crimes:
        return _empty_summary()

    # Aggregate by category and month, filtering out invalid data
    aggregated: dict[tuple[str, str], int] = defaultdict(int)
    skipped = 0
    for crime in all_crimes:
        cat = crime.get("category", "")
        month = crime.get("month", "")
        if not cat or not CRIME_MONTH_RE.match(month):
            skipped += 1
            continue
        aggregated[(cat, month)] += 1

    if skipped:
        logger.debug("Crime aggregation for %s: skipped %d records with missing category/month", clean, skipped)

    if not aggregated:
        return _empty_summary()

    # Atomic cache update: delete + insert in same transaction
    # flush() ensures the delete is sent before inserts, but both
    # are committed together — no window where data is missing
    db.query(CrimeStats).filter(CrimeStats.postcode == clean).delete()
    db.flush()

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


def _build_summary_from_crimes(crimes: list, cached: bool) -> dict:
    """Build summary directly from raw crime API records (no DB caching)."""
    categories: dict[str, int] = defaultdict(int)
    monthly: dict[str, int] = defaultdict(int)

    for crime in crimes:
        cat = crime.get("category", "")
        month = crime.get("month", "")
        if not cat or not CRIME_MONTH_RE.match(month):
            continue
        categories[cat] += 1
        monthly[month] += 1

    sorted_cats = dict(sorted(categories.items(), key=lambda x: -x[1]))
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


def _build_summary(stats: list, cached: bool) -> dict:
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
