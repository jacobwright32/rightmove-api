"""Enrichment endpoints — EPC data and crime statistics."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..enrichment.crime import get_crime_summary
from ..enrichment.epc import fetch_epc_for_postcode
from ..enrichment.flood import get_flood_risk
from ..enrichment.planning import get_planning_data
from ..models import Property
from ..schemas import (
    CrimeSummaryResponse,
    EPCEnrichmentResponse,
    FloodRiskResponse,
    PlanningResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/enrich", tags=["enrichment"])


@router.post("/epc/{postcode}", response_model=EPCEnrichmentResponse)
def enrich_epc(postcode: str, db: Session = Depends(get_db)):
    """Fetch EPC certificates for a postcode and update matching properties.

    Matches EPC records to existing properties by address similarity.
    Requires EPC_API_EMAIL and EPC_API_KEY to be configured.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {clean}. Scrape first.",
        )

    certificates = fetch_epc_for_postcode(clean)
    if not certificates:
        return EPCEnrichmentResponse(
            message=f"No EPC data found for {clean} (check API credentials)",
            properties_updated=0,
            certificates_found=0,
        )

    # Build address lookup for matching
    # EPC addresses are uppercase, our addresses may vary — normalize both
    epc_by_address: dict[str, dict] = {}
    for cert in certificates:
        addr = cert["address"].upper().strip()
        # Keep the most recent cert per address (API returns newest first)
        if addr not in epc_by_address:
            epc_by_address[addr] = cert

    updated = 0
    for prop in props:
        prop_addr = prop.address.upper().strip()
        # Try exact match first
        cert = epc_by_address.get(prop_addr)
        if not cert:
            # Try matching by house number + postcode
            # Extract leading number from address (e.g. "10" from "10 High Street, SW20 8NE")
            cert = _fuzzy_match(prop_addr, epc_by_address)

        if cert and cert.get("epc_rating"):
            prop.epc_rating = cert["epc_rating"]
            prop.epc_score = cert.get("epc_score")
            prop.epc_environment_impact = cert.get("environment_impact")
            prop.estimated_energy_cost = cert.get("estimated_energy_cost")
            updated += 1

    db.commit()
    logger.info("EPC enrichment for %s: %d/%d properties updated from %d certificates",
                clean, updated, len(props), len(certificates))

    return EPCEnrichmentResponse(
        message=f"Updated {updated}/{len(props)} properties with EPC data for {clean}",
        properties_updated=updated,
        certificates_found=len(certificates),
    )


def _fuzzy_match(prop_address: str, epc_lookup: dict[str, dict]) -> Optional[dict]:
    """Try to match a property address to an EPC certificate.

    Strips commas, extra spaces, and tries matching the first line of the address.
    """
    import re

    # Normalize: remove commas, collapse spaces
    norm = re.sub(r"[,]+", " ", prop_address).strip()
    norm = re.sub(r"\s+", " ", norm)

    for epc_addr, cert in epc_lookup.items():
        epc_norm = re.sub(r"[,]+", " ", epc_addr).strip()
        epc_norm = re.sub(r"\s+", " ", epc_norm)

        # Check if the normalized addresses match
        if norm == epc_norm:
            return cert

        # Check if the first part (house number + street) matches
        # E.g. "10 HIGH STREET" matches "10 HIGH STREET LONDON SW20 8NE"
        prop_parts = norm.split()
        epc_parts = epc_norm.split()
        if len(prop_parts) >= 2 and len(epc_parts) >= 2:
            # Match if first 2-3 words are the same (number + street name)
            if prop_parts[:3] == epc_parts[:3]:
                return cert
            if prop_parts[:2] == epc_parts[:2]:
                return cert

    return None


# Flood risk endpoint
flood_router = APIRouter(tags=["analytics"])


@flood_router.get(
    "/analytics/postcode/{postcode}/flood-risk",
    response_model=FloodRiskResponse,
)
def get_postcode_flood_risk(postcode: str, db: Session = Depends(get_db)):
    """Get flood risk assessment for a postcode.

    Uses the free Environment Agency Flood Monitoring API (no auth required).
    Caches risk_level on properties for the postcode.
    """
    clean = postcode.upper().strip()
    result = get_flood_risk(clean)

    # Cache the risk level on matching properties
    if result["risk_level"] != "unknown":
        props = db.query(Property).filter(Property.postcode == clean).all()
        for prop in props:
            prop.flood_risk_level = result["risk_level"]
        if props:
            db.commit()

    return FloodRiskResponse(
        postcode=clean,
        risk_level=result["risk_level"],
        flood_zone=result["flood_zone"],
        active_warnings=result["active_warnings"],
        description=result["description"],
    )


# Planning applications endpoint
planning_router = APIRouter(tags=["analytics"])


@planning_router.get(
    "/analytics/postcode/{postcode}/planning",
    response_model=PlanningResponse,
)
def get_postcode_planning(postcode: str, db: Session = Depends(get_db)):
    """Get nearby planning applications for a postcode.

    Uses the free Planning Data API (no auth required).
    Results are cached for 30 days.
    """
    clean = postcode.upper().strip()
    result = get_planning_data(db, clean)

    return PlanningResponse(
        postcode=clean,
        applications=result["applications"],
        total_count=result["total_count"],
        major_count=result["major_count"],
        cached=result["cached"],
    )


# Crime endpoint lives under analytics for consistency
crime_router = APIRouter(tags=["analytics"])


@crime_router.get(
    "/analytics/postcode/{postcode}/crime",
    response_model=CrimeSummaryResponse,
)
def get_postcode_crime(postcode: str, db: Session = Depends(get_db)):
    """Get crime statistics for a postcode area.

    Uses the free UK Police API (no auth required).
    Results are cached for 30 days.
    """
    clean = postcode.upper().strip()
    summary = get_crime_summary(db, clean)

    return CrimeSummaryResponse(
        postcode=clean,
        categories=summary["categories"],
        monthly_trend=summary["monthly_trend"],
        total_crimes=summary["total_crimes"],
        months_covered=summary["months_covered"],
        cached=summary["cached"],
    )
