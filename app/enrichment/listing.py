"""Active listing status enrichment service.

Checks each property's Rightmove house-prices detail page for listing
data embedded in the React Router turbo stream.  The ``propertyListing``
object tells us whether the property is currently advertised for sale (or
rent), when it was listed, and gives us a listing ID to build the URL.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..config import LISTING_FRESHNESS_HOURS, SCRAPER_DELAY_BETWEEN_REQUESTS
from ..models import Property
from ..scraper.rightmove import (
    _parse_turbo_stream,
    _request_with_retry,
    _resolve_object,
)

logger = logging.getLogger(__name__)

RIGHTMOVE_BASE = "https://www.rightmove.co.uk"


# ------------------------------------------------------------------
# Core: extract listing data from a single property's detail page
# ------------------------------------------------------------------

def _extract_listing_from_detail_page(url: str) -> Optional[dict]:
    """Fetch a house-prices detail page and extract listing status.

    Returns a dict with listing fields, or None on failure.
    """
    resp = _request_with_retry(url)
    if not resp:
        return None

    flat = _parse_turbo_stream(resp.text)
    if not flat:
        return None

    # Find the propertyListing object in the turbo stream
    pl_dict = None
    for i, item in enumerate(flat):
        if item == "propertyListing" and i + 1 < len(flat):
            raw = flat[i + 1]
            if isinstance(raw, dict):
                pl_dict = _resolve_object(flat, raw)
            break

    if not pl_dict:
        return {"listing_status": "not_listed"}

    channel = pl_dict.get("channel", "")
    status = pl_dict.get("status", {})
    published = status.get("published", False)
    archived = status.get("archived", True)
    listing_id = pl_dict.get("id")

    # Determine listing status
    if published and not archived:
        listing_status = "for_sale" if channel == "RES_BUY" else "not_listed"
    else:
        listing_status = "not_listed"

    # For not_listed, return early — no need to extract details
    if listing_status == "not_listed":
        return {"listing_status": "not_listed"}

    # Extract listing date from listingHistory
    lh = pl_dict.get("listingHistory", {})
    reason = lh.get("listingUpdateReason", "")
    listing_date = _parse_listing_date(reason)
    if not listing_date:
        listing_date = pl_dict.get("advertisedFrom")

    # Build listing URL
    listing_url = f"{RIGHTMOVE_BASE}/properties/{listing_id}" if listing_id else None

    result = {
        "listing_status": listing_status,
        "listing_date": listing_date,
        "listing_url": listing_url,
        "listing_price": None,
        "listing_price_display": reason or None,
    }

    # For currently-listed-for-sale properties, try to get the asking price
    if listing_status == "for_sale" and listing_url:
        price_info = _fetch_listing_price(listing_url)
        if price_info:
            result["listing_price"] = price_info.get("price")
            result["listing_price_display"] = price_info.get("display")

    return result


def _parse_listing_date(reason: str) -> Optional[str]:
    """Parse a date from listingUpdateReason like 'Added on 03/02/2026'."""
    if not reason:
        return None
    match = re.search(r"(\d{2}/\d{2}/\d{4})", reason)
    if match:
        return match.group(1)
    return None


def _fetch_listing_price(listing_url: str) -> Optional[dict]:
    """Try to extract the asking price from the listing page title.

    Rightmove listing page titles follow patterns like:
      "3 bed house for sale, Guide Price £450,000 in London | Rightmove"
      "2 bed flat for sale, £325,000 in Somewhere | Rightmove"
    """
    resp = _request_with_retry(listing_url)
    if not resp:
        return None

    # Try turbo stream first (some listing pages have it)
    flat = _parse_turbo_stream(resp.text)
    if flat:
        for i, item in enumerate(flat):
            if isinstance(item, str) and item == "price" and i + 1 < len(flat):
                next_val = flat[i + 1]
                if isinstance(next_val, dict):
                    resolved = _resolve_object(flat, next_val)
                    amount = resolved.get("amount")
                    qualifier = resolved.get("qualifier", "")
                    display = resolved.get("displayPrice", "")
                    if not display and amount:
                        display = f"\u00a3{amount:,}"
                    if qualifier:
                        display = f"{qualifier} {display}"
                    return {"price": int(amount) if amount else None, "display": display}

    # Fallback: parse price from <title> tag
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")
    title = soup.find("title")
    if title:
        title_text = title.get_text(strip=True)
        # Match patterns like "£450,000" or "Guide Price £450,000"
        price_match = re.search(r"(?:Guide Price\s+|Offers? (?:Over|in the region of)\s+)?(£[\d,]+)", title_text)
        if price_match:
            display = price_match.group(0).strip()
            amount_str = price_match.group(1).replace("£", "").replace(",", "")
            try:
                return {"price": int(amount_str), "display": display}
            except ValueError:
                return {"price": None, "display": display}

    return None


def _apply_listing_to_property(
    prop: Property, listing: Optional[dict],
) -> None:
    """Write listing data (or not_listed defaults) onto a Property row."""
    now = datetime.now(timezone.utc)
    if listing and listing.get("listing_status") != "not_listed":
        prop.listing_status = listing["listing_status"]
        prop.listing_price = listing.get("listing_price")
        prop.listing_price_display = listing.get("listing_price_display")
        prop.listing_date = listing.get("listing_date")
        prop.listing_url = listing.get("listing_url")
    else:
        prop.listing_status = "not_listed"
        prop.listing_price = None
        prop.listing_price_display = None
        prop.listing_date = None
        prop.listing_url = None
    prop.listing_checked_at = now


# ------------------------------------------------------------------
# Freshness check
# ------------------------------------------------------------------

def _is_listing_fresh(prop: Property) -> bool:
    """Return True if listing data was checked recently enough."""
    if not prop.listing_checked_at:
        return False
    now = datetime.utcnow()
    checked = prop.listing_checked_at
    if checked.tzinfo is not None:
        checked = checked.replace(tzinfo=None)
    age_hours = (now - checked).total_seconds() / 3600
    return age_hours < LISTING_FRESHNESS_HOURS


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def check_property_listing(db: Session, property_id: int) -> Optional[dict]:
    """Check listing status for a single property.

    Returns cached data if fresh, otherwise scrapes the detail page.
    Returns None if property not found.
    """
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        return None

    stale = not _is_listing_fresh(prop)

    if stale and prop.url:
        url = prop.url
        if not url.startswith("http"):
            url = RIGHTMOVE_BASE + url

        listing = _extract_listing_from_detail_page(url)
        _apply_listing_to_property(prop, listing)
        db.commit()
        db.refresh(prop)
        stale = False

    return {
        "property_id": prop.id,
        "listing_status": prop.listing_status,
        "listing_price": prop.listing_price,
        "listing_price_display": prop.listing_price_display,
        "listing_date": prop.listing_date,
        "listing_url": prop.listing_url,
        "listing_checked_at": prop.listing_checked_at,
        "stale": stale,
    }


def enrich_postcode_listings(db: Session, postcode: str) -> dict:
    """Check listing status for all properties in a postcode.

    Visits each property's detail page to extract listing data.
    Returns summary dict.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        return {
            "listings_found": 0,
            "properties_matched": 0,
            "properties_not_listed": 0,
            "cached": False,
        }

    # Check if all properties are fresh
    if all(_is_listing_fresh(p) for p in props):
        matched = sum(
            1 for p in props
            if p.listing_status and p.listing_status != "not_listed"
        )
        not_listed = sum(
            1 for p in props
            if p.listing_status == "not_listed" or not p.listing_status
        )
        return {
            "listings_found": matched,
            "properties_matched": matched,
            "properties_not_listed": not_listed,
            "cached": True,
        }

    matched = 0
    not_listed = 0

    for i, prop in enumerate(props):
        if _is_listing_fresh(prop):
            # Already checked recently
            if prop.listing_status and prop.listing_status != "not_listed":
                matched += 1
            else:
                not_listed += 1
            continue

        if not prop.url:
            _apply_listing_to_property(prop, None)
            not_listed += 1
            continue

        # Rate limit between requests
        if i > 0:
            time.sleep(SCRAPER_DELAY_BETWEEN_REQUESTS)

        url = prop.url
        if not url.startswith("http"):
            url = RIGHTMOVE_BASE + url

        listing = _extract_listing_from_detail_page(url)
        _apply_listing_to_property(prop, listing)

        if prop.listing_status != "not_listed":
            matched += 1
        else:
            not_listed += 1

    db.commit()
    logger.info(
        "Listing enrichment for %s: %d for sale, %d not listed",
        clean, matched, not_listed,
    )

    return {
        "listings_found": matched,
        "properties_matched": matched,
        "properties_not_listed": not_listed,
        "cached": False,
    }
