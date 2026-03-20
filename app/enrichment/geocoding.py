"""Shared geocoding service using Postcodes.io (free, no auth).

Provides single and batch postcode-to-coordinates conversion.
"""

import logging
from typing import Optional

import httpx

from ..constants import GEOCODING_BATCH_TIMEOUT, GEOCODING_SINGLE_TIMEOUT, POSTCODES_IO_URL

logger = logging.getLogger(__name__)


def geocode_postcode(postcode: str) -> Optional[tuple]:
    """Convert a UK postcode to (lat, lng) via Postcodes.io."""
    try:
        resp = httpx.get(f"{POSTCODES_IO_URL}/{postcode}", timeout=GEOCODING_SINGLE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 200 and data.get("result"):
            lat = data["result"]["latitude"]
            lng = data["result"]["longitude"]
            return (lat, lng)
    except (httpx.RequestError, httpx.HTTPStatusError, KeyError) as e:
        logger.warning("Geocoding failed for %s: %s", postcode, e)
    return None


def _geocode_chunk(chunk: list) -> dict:
    """Geocode a single chunk of up to 100 postcodes."""
    results = {}
    try:
        resp = httpx.post(
            POSTCODES_IO_URL,
            json={"postcodes": chunk},
            timeout=GEOCODING_BATCH_TIMEOUT,
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
        logger.warning("Batch geocoding failed for chunk of %d: %s", len(chunk), e)
    return results


def batch_geocode_postcodes(postcodes: list, concurrent: bool = False) -> dict:
    """Batch geocode UK postcodes via Postcodes.io.

    Args:
        postcodes: List of postcode strings.
        concurrent: If True, fire multiple batch requests in parallel (10 threads).

    Returns:
        Dict mapping postcode -> (lat, lng). Missing postcodes are omitted.
    """
    chunks = [postcodes[i:i + 100] for i in range(0, len(postcodes), 100)]

    if not concurrent or len(chunks) <= 1:
        results = {}
        for chunk in chunks:
            results.update(_geocode_chunk(chunk))
        return results

    # Concurrent mode: fire up to 10 batch requests in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_geocode_chunk, chunk): chunk for chunk in chunks}
        for fut in as_completed(futs):
            try:
                results.update(fut.result())
            except Exception as e:
                logger.warning("Geocode thread failed: %s", e)
    return results
