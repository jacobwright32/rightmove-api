from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..export import SALES_DATA_DIR, save_property_parquet
from ..models import Property
from ..schemas import ExportResponse, PostcodeSummary, PostcodeStatus, PropertyBrief, PropertyDetail
from ..scraper.rightmove import scrape_postcode_from_listing

router = APIRouter(tags=["properties"])


@router.get("/properties", response_model=List[PropertyDetail])
def list_properties(
    postcode: Optional[str] = Query(default=None, description="Filter by postcode"),
    property_type: Optional[str] = Query(default=None, description="Filter by property type"),
    min_bedrooms: Optional[int] = Query(default=None, ge=0, description="Minimum bedrooms"),
    max_bedrooms: Optional[int] = Query(default=None, ge=0, description="Maximum bedrooms"),
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

    query = query.order_by(Property.created_at.desc()).offset(skip)
    if limit > 0:
        query = query.limit(limit)
    return query.all()


@router.get("/properties/{property_id}", response_model=PropertyDetail)
def get_property(property_id: int, db: Session = Depends(get_db)):
    """Get a single property with its full sale history."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/properties/postcode/{postcode}/status", response_model=PostcodeStatus)
def get_postcode_status(postcode: str, db: Session = Depends(get_db)):
    """Check if we have data for a postcode, with property count and last update time."""
    postcode_clean = postcode.upper().replace("-", "").replace(" ", "")
    props = db.query(Property).filter(func.replace(func.upper(Property.postcode), " ", "").like(f"%{postcode_clean}%")).all()
    if not props:
        return PostcodeStatus(has_data=False, property_count=0, last_updated=None)
    last_updated = max((p.updated_at or p.created_at) for p in props if p.updated_at or p.created_at)
    return PostcodeStatus(has_data=True, property_count=len(props), last_updated=last_updated)


@router.get("/postcodes/suggest/{partial}", response_model=List[str])
def suggest_postcodes(partial: str, db: Session = Depends(get_db)):
    """Suggest full postcodes for a partial input like 'SW20 8'.

    Checks the local DB first, then scrapes Rightmove for more matches.
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


@router.get("/postcodes", response_model=List[PostcodeSummary])
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
