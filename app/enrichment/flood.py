"""Flood risk assessment service.

Uses the free Environment Agency Flood Monitoring API (no auth required).
Geocodes postcodes via Postcodes.io.
"""

import logging

import httpx

from .geocoding import geocode_postcode

logger = logging.getLogger(__name__)

EA_FLOOD_AREAS_URL = "https://environment.data.gov.uk/flood-monitoring/id/floodAreas"
EA_FLOOD_WARNINGS_URL = "https://environment.data.gov.uk/flood-monitoring/id/floods"

# Risk level mapping based on flood zone proximity
RISK_LEVELS = {
    1: "very_low",
    2: "low",
    3: "medium",
}


def get_flood_risk(postcode: str) -> dict:
    """Assess flood risk for a postcode.

    Returns dict with:
        - risk_level: "very_low" | "low" | "medium" | "high" | "unknown"
        - flood_zone: int or None
        - active_warnings: list of warning dicts
        - description: human-readable explanation
    """
    coords = geocode_postcode(postcode)
    if not coords:
        return _unknown_result("Could not geocode postcode")

    lat, lng = coords

    # Fetch active flood warnings near this location
    warnings = _fetch_active_warnings(lat, lng)

    # Fetch flood risk areas to determine zone
    risk_level, flood_zone, description = _assess_risk_from_areas(lat, lng)

    # If there are active warnings, elevate risk
    if warnings and risk_level in ("very_low", "low"):
        risk_level = "medium"
        description = "Active flood warnings in the area"
    if any(w.get("severity") in ("Severe", "1") for w in warnings):
        risk_level = "high"
        description = "Severe flood warning in effect"

    return {
        "risk_level": risk_level,
        "flood_zone": flood_zone,
        "active_warnings": warnings,
        "description": description,
    }


def _fetch_active_warnings(lat: float, lng: float) -> list:
    """Fetch active flood warnings near coordinates from EA API."""
    try:
        resp = httpx.get(
            EA_FLOOD_WARNINGS_URL,
            params={"lat": str(lat), "long": str(lng), "dist": "5"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("EA flood warnings API returned %d", resp.status_code)
            return []
        data = resp.json()
        items = data.get("items", [])
        return [
            {
                "severity": item.get("severityLevel", "Unknown"),
                "message": item.get("message", ""),
                "area": item.get("description", item.get("eaAreaName", "")),
            }
            for item in items[:10]  # Cap at 10 warnings
        ]
    except (httpx.RequestError, httpx.HTTPStatusError, KeyError, ValueError) as e:
        logger.warning("EA flood warnings request failed: %s", e)
        return []


def _assess_risk_from_areas(
    lat: float, lng: float
) -> tuple:
    """Determine flood risk zone from EA flood areas near coordinates.

    Returns (risk_level, flood_zone, description).
    """
    try:
        resp = httpx.get(
            EA_FLOOD_AREAS_URL,
            params={"lat": str(lat), "long": str(lng), "dist": "1"},
            timeout=10,
        )
        if resp.status_code != 200:
            return ("unknown", None, "Could not determine flood risk")

        data = resp.json()
        items = data.get("items", [])

        if not items:
            return ("very_low", 1, "Not in a flood risk area")

        # Check for highest risk zone in nearby areas
        highest_zone = 1
        for item in items:
            notation = item.get("notation", "")
            # EA area notations often contain flood zone info
            if "Zone3" in notation or "zone3" in notation:
                highest_zone = max(highest_zone, 3)
            elif "Zone2" in notation or "zone2" in notation:
                highest_zone = max(highest_zone, 2)

        # If we found flood areas but couldn't parse zones,
        # the presence of areas means at least zone 2
        if highest_zone == 1 and items:
            highest_zone = 2

        risk_level = RISK_LEVELS.get(highest_zone, "medium")
        descriptions = {
            1: "Low probability of flooding",
            2: "Medium probability of flooding (Flood Zone 2)",
            3: "High probability of flooding (Flood Zone 3)",
        }
        return (risk_level, highest_zone, descriptions.get(highest_zone, ""))

    except (httpx.RequestError, httpx.HTTPStatusError, KeyError, ValueError) as e:
        logger.warning("EA flood areas request failed: %s", e)
        return ("unknown", None, "Could not determine flood risk")


def _unknown_result(message: str = "Unknown") -> dict:
    return {
        "risk_level": "unknown",
        "flood_zone": None,
        "active_warnings": [],
        "description": message,
    }
