"""Enrichment endpoints — EPC, transport, crime, flood, planning, bulk."""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..enrichment.broadband import enrich_postcode_broadband
from ..enrichment.bulk import get_coverage, get_status, start, stop
from ..enrichment.crime import get_crime_summary
from ..enrichment.epc import fetch_epc_for_postcode
from ..enrichment.flood import get_flood_risk
from ..enrichment.imd import enrich_postcode_imd
from ..enrichment.listing import check_property_listing, enrich_postcode_listings
from ..enrichment.planning import get_planning_data
from ..enrichment.schools import enrich_postcode_schools
from ..enrichment.transport import enrich_postcode_transport
from ..models import Property
from ..schemas import (
    BroadbandEnrichmentResponse,
    CrimeSummaryResponse,
    EPCEnrichmentResponse,
    FloodRiskResponse,
    IMDEnrichmentResponse,
    ListingEnrichmentResponse,
    PlanningResponse,
    PropertyListingResponse,
    SchoolsEnrichmentResponse,
    TransportEnrichmentResponse,
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


def _fuzzy_match(prop_address: str, epc_lookup: dict) -> Optional[dict]:
    """Try to match a property address to an EPC certificate.

    Strips commas, extra spaces, and tries matching the first line of the address.
    """
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


@router.post("/imd/{postcode}", response_model=IMDEnrichmentResponse)
def enrich_imd(postcode: str, db: Session = Depends(get_db)):
    """Enrich properties with IMD deprivation deciles via postcode→LSOA lookup.

    Downloads ONS NSPL (~120MB) and IMD 2019 (~5MB) on first call.
    All properties in the same postcode share the same deprivation scores.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {clean}. Scrape first.",
        )

    result = enrich_postcode_imd(db, clean)
    return IMDEnrichmentResponse(
        message=result["message"],
        properties_updated=result["properties_updated"],
        properties_skipped=result["properties_skipped"],
    )


@router.post("/schools/{postcode}", response_model=SchoolsEnrichmentResponse)
def enrich_schools(postcode: str, db: Session = Depends(get_db)):
    """Enrich properties with nearest school distances and Ofsted ratings.

    Downloads GIAS CSV (~65MB) and converts BNG→WGS84 on first call.
    Uses cKDTree for O(log n) nearest-neighbour lookups.
    Properties need lat/lng — those without are skipped.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {clean}. Scrape first.",
        )

    result = enrich_postcode_schools(db, clean)
    return SchoolsEnrichmentResponse(
        message=result["message"],
        properties_updated=result["properties_updated"],
        properties_skipped=result["properties_skipped"],
    )


@router.post("/broadband/{postcode}", response_model=BroadbandEnrichmentResponse)
def enrich_broadband(postcode: str, db: Session = Depends(get_db)):
    """Enrich properties with Ofcom broadband speed data.

    Downloads Ofcom Connected Nations data (~200MB) on first call.
    All properties in the same postcode share the same broadband metrics.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {clean}. Scrape first.",
        )

    result = enrich_postcode_broadband(db, clean)
    return BroadbandEnrichmentResponse(
        message=result["message"],
        properties_updated=result["properties_updated"],
        properties_skipped=result["properties_skipped"],
    )


@router.post("/transport/{postcode}", response_model=TransportEnrichmentResponse)
def enrich_transport(postcode: str, db: Session = Depends(get_db)):
    """Compute transport distances for all properties in a postcode.

    Downloads NaPTAN data on first call (~96MB, cached as parquet).
    Uses cKDTree for O(log n) nearest-neighbour lookups.
    Properties without coordinates are geocoded first.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {clean}. Scrape first.",
        )

    result = enrich_postcode_transport(db, clean)
    return TransportEnrichmentResponse(
        message=result["message"],
        properties_updated=result["properties_updated"],
        properties_skipped=result["properties_skipped"],
    )


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


# Listing status endpoint
listing_router = APIRouter(tags=["enrichment"])


@listing_router.get(
    "/properties/{property_id}/listing",
    response_model=PropertyListingResponse,
)
def get_property_listing(property_id: int, db: Session = Depends(get_db)):
    """Get current listing status for a single property.

    Returns cached data if fresh, otherwise scrapes Rightmove for the
    property's postcode and matches by address.
    """
    result = check_property_listing(db, property_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return PropertyListingResponse(**result)


@router.post("/listing/{postcode}", response_model=ListingEnrichmentResponse)
def enrich_listing(postcode: str, db: Session = Depends(get_db)):
    """Check which properties in a postcode are currently for sale on Rightmove.

    Scrapes Rightmove's for-sale search, matches to stored properties by address.
    Results are cached for LISTING_FRESHNESS_HOURS.
    """
    clean = postcode.upper().strip()
    props = db.query(Property).filter(Property.postcode == clean).all()
    if not props:
        raise HTTPException(
            status_code=404,
            detail=f"No properties found for postcode {clean}. Scrape first.",
        )

    result = enrich_postcode_listings(db, clean)
    return ListingEnrichmentResponse(
        postcode=clean,
        listings_found=result["listings_found"],
        properties_matched=result["properties_matched"],
        properties_not_listed=result["properties_not_listed"],
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


# ── Bulk enrichment endpoints ──────────────────────────────────────

bulk_router = APIRouter(prefix="/enrich", tags=["enrichment"])


@bulk_router.get("/bulk/coverage")
def bulk_coverage():
    """Get feature coverage statistics for all properties."""
    return get_coverage()


@bulk_router.get("/bulk/status")
def bulk_status():
    """Get current bulk enrichment status."""
    return get_status()


@bulk_router.post("/bulk/start")
def bulk_start(
    types: Optional[str] = None,
    delay: float = 3.0,
):
    """Start bulk enrichment in background.

    Args:
        types: Comma-separated enrichment types (default: all).
               Options: geocode, transport, epc, crime, flood, planning
        delay: Seconds between API calls (default: 3.0)
    """
    type_list = types.split(",") if types else None
    return start(types=type_list, delay=delay)


@bulk_router.post("/bulk/stop")
def bulk_stop():
    """Stop the running bulk enrichment."""
    return stop()
