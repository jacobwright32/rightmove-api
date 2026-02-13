import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..enrichment.geocoding import batch_geocode_postcodes
from ..export import SALES_DATA_DIR, save_property_parquet
from ..models import Property, Sale
from ..schemas import ExportResponse, PostcodeStatus, PostcodeSummary, PropertyDetail, PropertyGeoPoint
from ..scraper.scraper import scrape_postcode_from_listing

_OUTCODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)\s", re.IGNORECASE)

router = APIRouter(tags=["properties"])


@router.get("/properties", response_model=list[PropertyDetail])
def list_properties(
    postcode: Optional[str] = Query(default=None, description="Filter by postcode"),
    property_type: Optional[str] = Query(default=None, description="Filter by property type"),
    min_bedrooms: Optional[int] = Query(default=None, ge=0, description="Minimum bedrooms"),
    max_bedrooms: Optional[int] = Query(default=None, ge=0, description="Maximum bedrooms"),
    listing_only: Optional[bool] = Query(default=None, description="True=only for-sale listings, False=only properties with sales"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=0, ge=0, description="Max properties to return (0 = all)"),
    db: Session = Depends(get_db),
):
    """List properties with optional filters, pagination, and sale history."""
    query = db.query(Property).options(joinedload(Property.sales))

    if postcode:
        pc = postcode.upper().replace("-", "").replace(" ", "")
        query = query.filter(func.replace(func.upper(Property.postcode), " ", "").like(f"%{pc}%"))
    if property_type:
        query = query.filter(Property.property_type.ilike(f"%{property_type}%"))
    if min_bedrooms is not None:
        query = query.filter(Property.bedrooms >= min_bedrooms)
    if max_bedrooms is not None:
        query = query.filter(Property.bedrooms <= max_bedrooms)

    # Separate listing-only properties from sale-history properties
    if listing_only is True:
        query = query.filter(Property.listing_status == "for_sale")
    elif listing_only is False:
        query = query.filter(
            (Property.listing_status.is_(None)) | (Property.listing_status != "for_sale")
        )

    query = query.order_by(Property.created_at.desc()).offset(skip)
    if limit > 0:
        query = query.limit(limit)
    return query.all()


@router.get("/properties/geo", response_model=list[PropertyGeoPoint])
def get_properties_geo(
    postcode: Optional[str] = Query(default=None, description="Filter by postcode prefix"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Return properties with lat/lng coordinates for map display.

    Batch geocodes postcodes via Postcodes.io if coordinates are missing.
    """
    import logging
    logger = logging.getLogger(__name__)

    query = db.query(Property).filter(Property.postcode.isnot(None))

    if postcode:
        pc = postcode.upper().replace("-", "").replace(" ", "")
        query = query.filter(func.replace(func.upper(Property.postcode), " ", "").like(f"%{pc}%"))

    props = query.limit(limit).all()
    if not props:
        return []

    # Find postcodes that need geocoding
    needs_geocoding = set()
    for p in props:
        if p.latitude is None and p.postcode:
            needs_geocoding.add(p.postcode)

    # Batch geocode missing postcodes
    if needs_geocoding:
        coords = batch_geocode_postcodes(list(needs_geocoding))
        for p in props:
            if p.latitude is None and p.postcode and p.postcode in coords:
                lat, lng = coords[p.postcode]
                p.latitude = lat
                p.longitude = lng
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Failed to save geocoded coordinates")

    # Single query: latest sale price per property (avoids N+1)
    prop_ids = [p.id for p in props if p.latitude is not None]
    latest_sale_sub = (
        db.query(
            Sale.property_id,
            func.max(Sale.date_sold_iso).label("max_date"),
        )
        .filter(Sale.property_id.in_(prop_ids), Sale.price_numeric.isnot(None))
        .group_by(Sale.property_id)
        .subquery()
    )
    price_rows = (
        db.query(Sale.property_id, Sale.price_numeric)
        .join(
            latest_sale_sub,
            (Sale.property_id == latest_sale_sub.c.property_id)
            & (Sale.date_sold_iso == latest_sale_sub.c.max_date),
        )
        .filter(Sale.price_numeric.isnot(None))
        .all()
    )
    price_map = {row[0]: row[1] for row in price_rows}

    result = []
    for p in props:
        if p.latitude is None or p.longitude is None:
            continue
        result.append(PropertyGeoPoint(
            id=p.id,
            address=p.address,
            postcode=p.postcode,
            latitude=p.latitude,
            longitude=p.longitude,
            latest_price=price_map.get(p.id),
            property_type=p.property_type,
            bedrooms=p.bedrooms,
            epc_rating=p.epc_rating,
            flood_risk_level=p.flood_risk_level,
        ))

    return result


@router.get("/properties/{property_id}", response_model=PropertyDetail)
def get_property(property_id: int, db: Session = Depends(get_db)):
    """Get a single property with its full sale history."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/properties/{property_id}/similar", response_model=list[PropertyDetail])
def get_similar_properties(
    property_id: int,
    limit: int = Query(default=5, ge=1, le=20, description="Number of similar properties to return"),
    db: Session = Depends(get_db),
):
    """Find properties similar to the target based on type, bedrooms, and location."""
    # 1. Fetch target property
    target = (
        db.query(Property)
        .options(joinedload(Property.sales))
        .filter(Property.id == property_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Property not found")

    # 2. Get target's latest sale price_numeric
    target_latest_sale = (
        db.query(Sale)
        .filter(Sale.property_id == target.id, Sale.price_numeric.isnot(None))
        .order_by(Sale.date_sold_iso.desc())
        .first()
    )
    if not target_latest_sale:
        raise HTTPException(
            status_code=404,
            detail="Target property has no sales with price data",
        )
    target_price = target_latest_sale.price_numeric

    # 3. Extract outcode from postcode (e.g. "SW20" from "SW20 8NE")
    if not target.postcode:
        raise HTTPException(
            status_code=404,
            detail="Target property has no postcode",
        )
    outcode_match = _OUTCODE_RE.match(target.postcode.strip())
    if not outcode_match:
        raise HTTPException(
            status_code=404,
            detail="Could not extract outcode from target postcode",
        )
    target_outcode = outcode_match.group(1).upper()

    # 4. Build query for similar properties
    target_type = (target.property_type or "").strip()
    target_beds = target.bedrooms

    # Subquery: latest sale price per property
    latest_sale_sub = (
        db.query(
            Sale.property_id,
            func.max(Sale.date_sold_iso).label("max_date"),
        )
        .filter(Sale.price_numeric.isnot(None))
        .group_by(Sale.property_id)
        .subquery()
    )
    latest_price_sub = (
        db.query(
            Sale.property_id,
            Sale.price_numeric.label("latest_price"),
        )
        .join(
            latest_sale_sub,
            (Sale.property_id == latest_sale_sub.c.property_id)
            & (Sale.date_sold_iso == latest_sale_sub.c.max_date),
        )
        .filter(Sale.price_numeric.isnot(None))
        .subquery()
    )

    query = (
        db.query(Property)
        .options(joinedload(Property.sales))
        .join(latest_price_sub, Property.id == latest_price_sub.c.property_id)
        .filter(Property.id != target.id)
    )

    # Same outcode prefix
    query = query.filter(
        func.upper(Property.postcode).like(f"{target_outcode} %")
    )

    # Property type match (case-insensitive)
    if target_type:
        query = query.filter(func.upper(Property.property_type) == target_type.upper())

    # Bedrooms within +/- 1
    if target_beds is not None:
        query = query.filter(
            Property.bedrooms >= target_beds - 1,
            Property.bedrooms <= target_beds + 1,
        )

    # Order by price proximity and limit
    query = query.order_by(func.abs(latest_price_sub.c.latest_price - target_price))
    query = query.limit(limit)

    results = query.all()
    return results


@router.get("/properties/postcode/{postcode}/status", response_model=PostcodeStatus)
def get_postcode_status(postcode: str, db: Session = Depends(get_db)):
    """Check if we have data for a postcode, with property count and last update time."""
    postcode_clean = postcode.upper().replace("-", "").replace(" ", "")
    props = db.query(Property).filter(func.replace(func.upper(Property.postcode), " ", "").like(f"%{postcode_clean}%")).all()
    if not props:
        return PostcodeStatus(has_data=False, property_count=0, last_updated=None)
    last_updated = max((p.updated_at or p.created_at) for p in props if p.updated_at or p.created_at)
    return PostcodeStatus(has_data=True, property_count=len(props), last_updated=last_updated)


@router.get("/postcodes/suggest/{partial}", response_model=list[str])
def suggest_postcodes(partial: str, db: Session = Depends(get_db)):
    """Suggest full postcodes for a partial input like 'SW20 8'.

    Checks the local DB first, then scrapes the source site for more matches.
    """
    partial_clean = partial.upper().replace("-", "").replace(" ", "")

    # Check DB for known postcodes matching the partial
    db_postcodes = (
        db.query(Property.postcode)
        .filter(
            Property.postcode.isnot(None),
            func.replace(func.upper(Property.postcode), " ", "").like(f"{partial_clean}%"),
        )
        .distinct()
        .all()
    )
    found = {row[0] for row in db_postcodes if row[0]}

    # If we don't have many, do a quick Rightmove scrape to discover more
    if len(found) < 5:
        try:
            properties = scrape_postcode_from_listing(partial_clean, max_properties=50, pages=1)
            for p in properties:
                if p.postcode:
                    found.add(p.postcode)
        except Exception:
            pass  # If scrape fails, return what we have from DB

    return sorted(found)


@router.get("/postcodes", response_model=list[PostcodeSummary])
def list_postcodes(db: Session = Depends(get_db)):
    """List all scraped postcodes with property counts."""
    results = (
        db.query(Property.postcode, func.count(Property.id).label("property_count"))
        .filter(Property.postcode.isnot(None))
        .group_by(Property.postcode)
        .order_by(func.count(Property.id).desc())
        .all()
    )
    return [
        PostcodeSummary(postcode=row.postcode, property_count=row.property_count)
        for row in results
    ]


@router.post("/export/{postcode}", response_model=ExportResponse)
def export_sales_data(postcode: str, db: Session = Depends(get_db)):
    """Export all properties and their sales for a postcode to parquet files.

    Saves to sales_data/{outcode}/{property_name}.parquet with each file
    containing all sales for a single property.
    """
    pc_clean = postcode.upper().replace("-", "").replace(" ", "")
    props = (
        db.query(Property)
        .options(joinedload(Property.sales))
        .filter(func.replace(func.upper(Property.postcode), " ", "").like(f"%{pc_clean}%"))
        .all()
    )

    if not props:
        raise HTTPException(status_code=404, detail=f"No properties found for '{postcode}'")

    files_written = sum(1 for prop in props if save_property_parquet(prop))

    return ExportResponse(
        message=f"Exported {files_written} properties for '{postcode}'",
        properties_exported=len(props),
        files_written=files_written,
        output_dir=str(SALES_DATA_DIR),
    )
