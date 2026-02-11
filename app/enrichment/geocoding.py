"""Shared geocoding service using Postcodes.io (free, no auth).

Provides single and batch postcode-to-coordinates conversion.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes"


def geocode_postcode(postcode: str) -> Optional[tuple]:
    """Convert a UK postcode to (lat, lng) via Postcodes.io."""
    try:
        resp = httpx.get(f"{POSTCODES_IO_URL}/{postcode}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 200 and data.get("result"):
            lat = data["result"]["latitude"]
            lng = data["result"]["longitude"]
            return (lat, lng)
    except (httpx.RequestError, httpx.HTTPStatusError, KeyError) as e:
        logger.warning("Geocoding failed for %s: %s", postcode, e)
    return None


def batch_geocode_postcodes(postcodes: list) -> dict:
    """Batch geocode UK postcodes via Postcodes.io.

    Args:
        postcodes: List of postcode strings (max 100 per API call).

    Returns:
        Dict mapping postcode -> (lat, lng). Missing postcodes are omitted.
    """
    results = {}
    # Postcodes.io accepts max 100 per batch request
    for i in range(0, len(postcodes), 100):
        chunk = postcodes[i:i + 100]
        try:
            resp = httpx.post(
                POSTCODES_IO_URL,
                json={"postcodes": chunk},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("result", []):
                if item and item.get("result"):
                    result = item["result"]
                    pc = result.get("postcode", item.get("query", ""))
                    lat = result.get("latitude")
                    lng = result.get("longitude")
                    if pc and lat is not None and lng is not None:
                        results[pc] = (lat, lng)
        except (httpx.RequestError, httpx.HTTPStatusError, KeyError, ValueError) as e:
            logger.warning("Batch geocoding failed for chunk starting at %d: %s", i, e)

    return results
