"""Active listing status enrichment service.

Scrapes Rightmove's for-sale search to determine which
properties in our database are currently listed for sale.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import LISTING_FRESHNESS_HOURS
from ..models import Property
from ..scraper.rightmove import _request_with_retry

logger = logging.getLogger(__name__)

RIGHTMOVE_SEARCH_URL = "https://www.rightmove.co.uk/property-for-sale/find.html"
RIGHTMOVE_BASE = "https://www.rightmove.co.uk"


def scrape_listings_for_postcode(postcode: str) -> list:
    """Fetch active for-sale listings from Rightmove for a postcode.

    Parses the window.jsonModel JSON blob from the search results page.
    Returns list of dicts with normalized listing data.
    """
    clean = postcode.upper().strip()
    url = RIGHTMOVE_SEARCH_URL
    params = {
        "searchLocation": clean,
        "sortType": "6",  # Sort by most recent
        "propertyTypes": "",
        "includeSSTC": "true",
    }

    resp = _request_with_retry(url, params=params)
    if not resp:
        logger.warning("Failed to fetch Rightmove for-sale search for %s", clean)
        return []

    return _parse_search_results(resp.text)


def _parse_search_results(html: str) -> list:
    """Extract listings from Rightmove search page HTML.

    Looks for window.jsonModel = {...} in script tags.
    """
    soup = BeautifulSoup(html, "lxml")

    # Find the script tag containing window.jsonModel
    json_model = None
    for script in soup.find_all("script"):
        text = script.string or ""
        match = re.search(r"window\.jsonModel\s*=\s*({.+?})\s*;?\s*$", text, re.DOTALL)
        if match:
            try:
                json_model = json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse window.jsonModel JSON")
            break

    if not json_model:
        logger.warning("Could not find window.jsonModel in search results")
        return []

    properties = json_model.get("properties", [])
    if not properties:
        return []

    listings = []
    for prop in properties:
        listing = _normalize_listing(prop)
        if listing:
            listings.append(listing)

    logger.info("Parsed %d active listings from Rightmove search", len(listings))
    return listings


def _normalize_listing(raw: dict) -> Optional[dict]:
    """Normalize a single listing from window.jsonModel format."""
    address = raw.get("displayAddress", "")
    if not address:
        return None

    # Extract price info
    price_data = raw.get("price", {})
    price_amount = price_data.get("amount")
    display_prices = price_data.get("displayPrices", [])
    price_display = ""
    if display_prices:
        price_display = display_prices[0].get("displayPrice", "")

    # Extract listing date
    listing_update = raw.get("listingUpdate", {})
    listing_date = listing_update.get("listingUpdateDate", "")

    # Extract status
    display_status = raw.get("displayStatus", "").strip().lower()
    if "under offer" in display_status:
        status = "under_offer"
    elif "sold" in display_status or "stc" in display_status:
        status = "sold_stc"
    else:
        status = "for_sale"

    # Build listing URL
    property_url = raw.get("propertyUrl", "")
    if property_url and not property_url.startswith("http"):
        property_url = RIGHTMOVE_BASE + property_url

    return {
        "address": address.upper().strip(),
        "status": status,
        "price": int(price_amount) if price_amount else None,
        "price_display": price_display,
        "listing_date": listing_date,
        "listing_url": property_url,
    }


def _fuzzy_match_address(
    prop_address: str, listings_by_address: dict
) -> Optional[dict]:
    """Try to match a property address to a scraped listing.

    Normalizes both addresses and compares by first 2-3 words.
    """
    norm = re.sub(r"[,]+", " ", prop_address).strip()
    norm = re.sub(r"\s+", " ", norm).upper()

    for listing_addr, listing in listings_by_address.items():
        listing_norm = re.sub(r"[,]+", " ", listing_addr).strip()
        listing_norm = re.sub(r"\s+", " ", listing_norm).upper()

        if norm == listing_norm:
            return listing

        prop_parts = norm.split()
        listing_parts = listing_norm.split()
        if len(prop_parts) >= 2 and len(listing_parts) >= 2:
            if prop_parts[:3] == listing_parts[:3]:
                return listing
            if prop_parts[:2] == listing_parts[:2]:
                return listing

    return None


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


def enrich_postcode_listings(db: Session, postcode: str) -> dict:
    """Scrape Rightmove for-sale search and match to stored properties.

    Updates listing fields on all Property rows for this postcode.
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
        matched = sum(1 for p in props if p.listing_status and p.listing_status != "not_listed")
        not_listed = sum(1 for p in props if p.listing_status == "not_listed")
        return {
            "listings_found": matched,
            "properties_matched": matched,
            "properties_not_listed": not_listed,
            "cached": True,
        }

    # Scrape listings
    listings = scrape_listings_for_postcode(clean)
    listings_by_address = {}
    for listing in listings:
        addr = listing["address"]
        if addr not in listings_by_address:
            listings_by_address[addr] = listing

    now = datetime.now(timezone.utc)
    matched = 0
    not_listed = 0

    for prop in props:
        prop_addr = prop.address.upper().strip()
        listing = listings_by_address.get(prop_addr)
        if not listing:
            listing = _fuzzy_match_address(prop_addr, listings_by_address)

        if listing:
            prop.listing_status = listing["status"]
            prop.listing_price = listing["price"]
            prop.listing_price_display = listing["price_display"]
            prop.listing_date = listing["listing_date"]
            prop.listing_url = listing["listing_url"]
            matched += 1
        else:
            prop.listing_status = "not_listed"
            prop.listing_price = None
            prop.listing_price_display = None
            prop.listing_date = None
            prop.listing_url = None
            not_listed += 1

        prop.listing_checked_at = now

    db.commit()
    logger.info(
        "Listing enrichment for %s: %d matched, %d not listed (from %d scraped)",
        clean, matched, not_listed, len(listings),
    )

    return {
        "listings_found": len(listings),
        "properties_matched": matched,
        "properties_not_listed": not_listed,
        "cached": False,
    }


def check_property_listing(db: Session, property_id: int) -> Optional[dict]:
    """Check listing status for a single property.

    Returns cached data if fresh, otherwise scrapes the postcode.
    Returns None if property not found.
    """
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        return None

    stale = not _is_listing_fresh(prop)

    # If stale and we have a postcode, scrape
    if stale and prop.postcode:
        enrich_postcode_listings(db, prop.postcode)
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
