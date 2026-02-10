"""EPC (Energy Performance Certificate) data enrichment service.

Uses the free API at https://epc.opendatacommunities.org/
Requires EPC_API_EMAIL and EPC_API_KEY in config.
"""

import base64
import logging
from typing import Optional

import httpx

from ..config import EPC_API_EMAIL, EPC_API_KEY

logger = logging.getLogger(__name__)

EPC_BASE_URL = "https://epc.opendatacommunities.org/api/v1/domestic/search"

# Map EPC rating letters to display colors (for frontend reference)
EPC_RATING_COLORS = {
    "A": "#00C853",
    "B": "#66BB6A",
    "C": "#C6FF00",
    "D": "#FFEB3B",
    "E": "#FFB300",
    "F": "#FF6D00",
    "G": "#D50000",
}


def _get_auth_header() -> Optional[str]:
    """Build Basic auth header from configured credentials."""
    if not EPC_API_EMAIL or not EPC_API_KEY:
        return None
    token = base64.b64encode(f"{EPC_API_EMAIL}:{EPC_API_KEY}".encode()).decode()
    return f"Basic {token}"


def fetch_epc_for_postcode(postcode: str) -> list[dict]:
    """Fetch EPC certificates for a postcode.

    Returns list of dicts with keys:
        address, epc_rating, epc_score, environment_impact, estimated_energy_cost
    """
    auth = _get_auth_header()
    if not auth:
        logger.warning("EPC API credentials not configured — set EPC_API_EMAIL and EPC_API_KEY")
        return []

    headers = {
        "Authorization": auth,
        "Accept": "application/json",
    }

    try:
        resp = httpx.get(
            EPC_BASE_URL,
            params={"postcode": postcode, "size": 500},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning("EPC API error for %s: %s %s", postcode, e.response.status_code, e.response.text[:200])
        return []
    except httpx.RequestError as e:
        logger.warning("EPC API request failed for %s: %s", postcode, e)
        return []

    data = resp.json()
    rows = data.get("rows", [])

    results = []
    for row in rows:
        # Sum up energy costs (heating + hot water + lighting)
        energy_cost = 0
        for cost_key in ("heating-cost-current", "hot-water-cost-current", "lighting-cost-current"):
            val = row.get(cost_key)
            if val:
                try:
                    energy_cost += int(float(val))
                except (ValueError, TypeError):
                    pass

        results.append({
            "address": row.get("address", "").upper(),
            "epc_rating": row.get("current-energy-rating", ""),
            "epc_score": _safe_int(row.get("current-energy-efficiency")),
            "environment_impact": _safe_int(row.get("environment-impact-current")),
            "estimated_energy_cost": energy_cost or None,
        })

    logger.info("EPC: fetched %d certificates for %s", len(results), postcode)
    return results


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None
