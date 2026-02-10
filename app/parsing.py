"""Utilities for parsing Rightmove price and date strings into structured formats."""

import re
from datetime import datetime
from typing import Optional

# Month abbreviation mapping for date parsing
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_price_to_int(price: str) -> Optional[int]:
    """Parse a price string like '£450,000' into an integer 450000.

    Handles various formats: '£450,000', '£450000', '450,000', '£1,200,000'.
    Returns None if the string cannot be parsed.
    """
    if not price:
        return None
    cleaned = price.replace("\u00a3", "").replace("\u00c2", "").replace(",", "").strip()
    match = re.search(r"(\d+)", cleaned)
    if match:
        return int(match.group(1))
    return None


def parse_date_to_iso(date_str: str) -> Optional[str]:
    """Parse a date string like '4 Nov 2023' into ISO format '2023-11-04'.

    Handles formats: '4 Nov 2023', '04 Nov 2023', '15 Mar 2021'.
    Returns None if the string cannot be parsed.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    match = re.match(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", date_str)
    if not match:
        return None
    day = int(match.group(1))
    month_str = match.group(2).lower()[:3]
    year = int(match.group(3))
    month = _MONTHS.get(month_str)
    if month is None:
        return None
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None
