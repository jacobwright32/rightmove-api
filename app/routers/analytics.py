import re
import statistics
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Property, Sale
from ..schemas import (
    BedroomDistribution,
    MarketOverview,
    PostcodeAnalytics,
    PostcodeComparison,
    PriceRangeBucket,
    PriceTrendPoint,
    PropertyTypeBreakdown,
    SalesVolumePoint,
    StreetComparison,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/market-overview", response_model=MarketOverview)
def get_market_overview(db: Session = Depends(get_db)):
    """Database-wide aggregated statistics across all properties and sales."""
    # 1. Count distinct postcodes, properties, sales
    total_postcodes = (
        db.query(func.count(func.distinct(Property.postcode)))
        .filter(Property.postcode.isnot(None))
        .scalar()
    ) or 0
    total_properties = db.query(func.count(Property.id)).scalar() or 0
    total_sales = db.query(func.count(Sale.id)).scalar() or 0

    # 2. Date range (earliest/latest date_sold_iso)
    earliest_date = db.query(func.min(Sale.date_sold_iso)).filter(Sale.date_sold_iso.isnot(None)).scalar()
    latest_date = db.query(func.max(Sale.date_sold_iso)).filter(Sale.date_sold_iso.isnot(None)).scalar()
    date_range = {"earliest": earliest_date, "latest": latest_date}

    # 3. Average and median price_numeric across all sales
    all_prices = [
        row[0]
        for row in db.query(Sale.price_numeric).filter(Sale.price_numeric.isnot(None)).all()
    ]
    avg_price: Optional[float] = round(statistics.mean(all_prices)) if all_prices else None
    median_price: Optional[float] = round(statistics.median(all_prices)) if all_prices else None

    # 4. Price distribution buckets
    buckets = [
        ("Under \u00a3200k", 0, 200000),
        ("\u00a3200k-\u00a3400k", 200000, 400000),
        ("\u00a3400k-\u00a3600k", 400000, 600000),
        ("\u00a3600k-\u00a31M", 600000, 1000000),
        ("Over \u00a31M", 1000000, None),
    ]
    price_distribution = []
    for label, low, high in buckets:
        q = db.query(func.count(Sale.id)).filter(Sale.price_numeric.isnot(None))
        q = q.filter(Sale.price_numeric >= low)
        if high is not None:
            q = q.filter(Sale.price_numeric < high)
        count = q.scalar() or 0
        price_distribution.append(PriceRangeBucket(range=label, count=count))

    # 5. Top 10 postcodes by sale volume
    top_pc_rows = (
        db.query(
            Property.postcode,
            func.count(Sale.id).label("sale_count"),
            func.avg(Sale.price_numeric).label("avg_price"),
        )
        .join(Sale, Sale.property_id == Property.id)
        .filter(Property.postcode.isnot(None))
        .group_by(Property.postcode)
        .order_by(func.count(Sale.id).desc())
        .limit(10)
        .all()
    )
    top_postcodes = [
        PostcodeComparison(
            postcode=row[0],
            avg_price=round(row[2]) if row[2] else None,
            count=row[1],
        )
        for row in top_pc_rows
    ]

    # 6. Property type breakdown
    type_rows = (
        db.query(
            Sale.property_type,
            Property.property_type,
            Sale.price_numeric,
        )
        .join(Property, Sale.property_id == Property.id)
        .all()
    )
    type_data: dict = defaultdict(list)
    for sale_type, prop_type, price in type_rows:
        ptype = sale_type or prop_type or "Unknown"
        ptype = ptype.strip().upper() or "Unknown"
        if price is not None:
            type_data[ptype].append(price)
    property_types = sorted(
        [
            PropertyTypeBreakdown(
                property_type=ptype,
                count=len(prices),
                avg_price=round(statistics.mean(prices)) if prices else None,
            )
            for ptype, prices in type_data.items()
        ],
        key=lambda x: x.count,
        reverse=True,
    )

    # 7. Bedroom distribution
    bed_rows = (
        db.query(Property.bedrooms, Sale.price_numeric)
        .join(Sale, Sale.property_id == Property.id)
        .filter(Property.bedrooms.isnot(None))
        .all()
    )
    bed_data: dict = defaultdict(list)
    for beds, price in bed_rows:
        if price is not None:
            bed_data[beds].append(price)
    bedroom_distribution = sorted(
        [
            BedroomDistribution(
                bedrooms=beds,
                count=len(prices),
                avg_price=round(statistics.mean(prices)) if prices else None,
            )
            for beds, prices in bed_data.items()
        ],
        key=lambda x: x.bedrooms,
    )

    # 8. Yearly sales volume
    year_rows = (
        db.query(Sale.date_sold_iso)
        .filter(Sale.date_sold_iso.isnot(None))
        .all()
    )
    year_counts: dict = defaultdict(int)
    for (date_iso,) in year_rows:
        year = int(date_iso[:4])
        year_counts[year] += 1
    yearly_trends = [
        SalesVolumePoint(year=year, count=count)
        for year, count in sorted(year_counts.items())
    ]

    # 9. Monthly price trends
    monthly_rows = (
        db.query(Sale.date_sold_iso, Sale.price_numeric)
        .filter(Sale.date_sold_iso.isnot(None), Sale.price_numeric.isnot(None))
        .all()
    )
    monthly: dict = defaultdict(list)
    for date_iso, price in monthly_rows:
        month = date_iso[:7]
        monthly[month].append(price)
    price_trends = [
        PriceTrendPoint(
            month=m,
            avg_price=round(statistics.mean(p)),
            median_price=round(statistics.median(p)),
            min_price=min(p),
            max_price=max(p),
            count=len(p),
        )
        for m, p in sorted(monthly.items())
    ]

    return MarketOverview(
        total_postcodes=total_postcodes,
        total_properties=total_properties,
        total_sales=total_sales,
        date_range=date_range,
        avg_price=avg_price,
        median_price=median_price,
        price_distribution=price_distribution,
        top_postcodes=top_postcodes,
        property_types=property_types,
        bedroom_distribution=bedroom_distribution,
        yearly_trends=yearly_trends,
        price_trends=price_trends,
    )


# --- Postcode-specific analytics ---

postcode_router = APIRouter(prefix="/analytics/postcode", tags=["analytics"])


def _get_sales_for_postcode(db: Session, postcode: str):
    """Get all sales joined with properties for a given postcode."""
    postcode_clean = postcode.upper().replace("-", "").replace(" ", "")
    return (
        db.query(Sale, Property)
        .join(Property, Sale.property_id == Property.id)
        .filter(func.replace(func.upper(Property.postcode), " ", "").like(f"%{postcode_clean}%"))
        .all()
    )


_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
_STREET_SUFFIXES = re.compile(
    r"\b(Road|Street|Avenue|Lane|Drive|Close|Way|Gardens|Crescent|Place|"
    r"Terrace|Court|Hill|Park|Grove|Square|Walk|Rise|Row|Mews|Yard|"
    r"Passage|Parade|Green|Circus|Gate|View|Wharf|Linkway|Westway)\b",
    re.IGNORECASE,
)
_SKIP_CITIES = {"london", "england", "uk", "united kingdom"}
_NUMBER_ONLY = re.compile(r"^(flat|unit|apt|apartment)?\s*\d+[a-zA-Z]?$", re.IGNORECASE)
_AREAS = {
    "raynes park", "wimbledon chase", "west wimbledon", "east wimbledon",
    "wimbledon park", "colliers wood", "south wimbledon", "morden park",
}


def _extract_street(address: str) -> str:
    """Extract the street name from a UK address string.

    E.g. 'Flat 5, 14, Coombe Lane, London SW20 8ND' -> 'Coombe Lane'
         '1, Woodlands, Raynes Park, London SW20 9JF' -> 'Woodlands'
    """
    if not address:
        return "Unknown"

    cleaned = _POSTCODE_RE.sub("", address).strip().rstrip(",").strip()
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    meaningful = [
        p for p in parts
        if p.lower() not in _SKIP_CITIES and not _NUMBER_ONLY.match(p)
    ]

    # Strategy 1: first part with a known street suffix that isn't a neighbourhood
    for part in meaningful:
        if _STREET_SUFFIXES.search(part) and part.lower() not in _AREAS:
            street = re.sub(r"^(\d+[a-zA-Z]?[\s-]*)+", "", part).strip()
            if street:
                return street

    # Strategy 2: first meaningful part (building/estate name)
    for part in meaningful:
        street = re.sub(r"^(\d+[a-zA-Z]?[\s-]*)+", "", part).strip()
        if street and street.lower() not in _AREAS:
            return street

    # Strategy 3: any meaningful part
    for part in meaningful:
        street = re.sub(r"^(\d+[a-zA-Z]?[\s-]*)+", "", part).strip()
        if street:
            return street

    return "Unknown"


@postcode_router.get("/{postcode}/price-trends", response_model=list[PriceTrendPoint])
def get_price_trends(postcode: str, db: Session = Depends(get_db)):
    """Monthly average/median/min/max prices for a postcode."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    # Group prices by month (YYYY-MM)
    monthly: dict[str, list[int]] = defaultdict(list)
    for sale, _prop in rows:
        if sale.price_numeric and sale.date_sold_iso:
            month = sale.date_sold_iso[:7]  # "2023-11"
            monthly[month].append(sale.price_numeric)

    result = []
    for month in sorted(monthly.keys()):
        prices = monthly[month]
        result.append(PriceTrendPoint(
            month=month,
            avg_price=round(statistics.mean(prices)),
            median_price=round(statistics.median(prices)),
            min_price=min(prices),
            max_price=max(prices),
            count=len(prices),
        ))
    return result


@postcode_router.get("/{postcode}/property-types", response_model=list[PropertyTypeBreakdown])
def get_property_types(postcode: str, db: Session = Depends(get_db)):
    """Count and average price per property type."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    type_data: dict[str, list[int]] = defaultdict(list)
    for sale, _prop in rows:
        ptype = sale.property_type or _prop.property_type or "Unknown"
        ptype = ptype.strip().upper() or "Unknown"
        if sale.price_numeric:
            type_data[ptype].append(sale.price_numeric)

    return sorted(
        [
            PropertyTypeBreakdown(
                property_type=ptype,
                count=len(prices),
                avg_price=round(statistics.mean(prices)) if prices else None,
            )
            for ptype, prices in type_data.items()
        ],
        key=lambda x: x.count,
        reverse=True,
    )


@postcode_router.get("/{postcode}/street-comparison", response_model=list[StreetComparison])
def get_street_comparison(postcode: str, db: Session = Depends(get_db)):
    """Average price per street, extracted from property addresses."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    street_data: dict[str, list[int]] = defaultdict(list)
    for sale, prop in rows:
        street = _extract_street(prop.address)
        if sale.price_numeric:
            street_data[street].append(sale.price_numeric)

    return sorted(
        [
            StreetComparison(
                street=street,
                avg_price=round(statistics.mean(prices)) if prices else None,
                count=len(prices),
            )
            for street, prices in street_data.items()
        ],
        key=lambda x: x.avg_price or 0,
        reverse=True,
    )


@postcode_router.get("/{postcode}/postcode-comparison", response_model=list[PostcodeComparison])
def get_postcode_comparison(postcode: str, db: Session = Depends(get_db)):
    """Average price per full postcode within the searched area."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    pc_data: dict[str, list[int]] = defaultdict(list)
    for sale, prop in rows:
        if sale.price_numeric and prop.postcode:
            pc_data[prop.postcode].append(sale.price_numeric)

    return sorted(
        [
            PostcodeComparison(
                postcode=pc,
                avg_price=round(statistics.mean(prices)) if prices else None,
                count=len(prices),
            )
            for pc, prices in pc_data.items()
        ],
        key=lambda x: x.avg_price or 0,
        reverse=True,
    )


@postcode_router.get("/{postcode}/bedroom-distribution", response_model=list[BedroomDistribution])
def get_bedroom_distribution(postcode: str, db: Session = Depends(get_db)):
    """Count and average price per bedroom count."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    bed_data: dict[int, list[int]] = defaultdict(list)
    for sale, prop in rows:
        if prop.bedrooms is not None and sale.price_numeric:
            bed_data[prop.bedrooms].append(sale.price_numeric)

    return sorted(
        [
            BedroomDistribution(
                bedrooms=beds,
                count=len(prices),
                avg_price=round(statistics.mean(prices)) if prices else None,
            )
            for beds, prices in bed_data.items()
        ],
        key=lambda x: x.bedrooms,
    )


@postcode_router.get("/{postcode}/sales-volume", response_model=list[SalesVolumePoint])
def get_sales_volume(postcode: str, db: Session = Depends(get_db)):
    """Sales count per year."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    year_counts: dict[int, int] = defaultdict(int)
    for sale, _prop in rows:
        if sale.date_sold_iso:
            year = int(sale.date_sold_iso[:4])
            year_counts[year] += 1

    return [
        SalesVolumePoint(year=year, count=count)
        for year, count in sorted(year_counts.items())
    ]


@postcode_router.get("/{postcode}/summary", response_model=PostcodeAnalytics)
def get_summary(postcode: str, db: Session = Depends(get_db)):
    """All analytics combined in a single call."""
    rows = _get_sales_for_postcode(db, postcode)
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this postcode")

    # Price trends
    monthly: dict[str, list[int]] = defaultdict(list)
    type_data: dict[str, list[int]] = defaultdict(list)
    street_data: dict[str, list[int]] = defaultdict(list)
    pc_data: dict[str, list[int]] = defaultdict(list)
    bed_data: dict[int, list[int]] = defaultdict(list)
    year_counts: dict[int, int] = defaultdict(int)

    for sale, prop in rows:
        has_price = sale.price_numeric is not None
        has_date = sale.date_sold_iso is not None

        if has_price and has_date:
            monthly[sale.date_sold_iso[:7]].append(sale.price_numeric)
            year_counts[int(sale.date_sold_iso[:4])] += 1

        if has_price:
            ptype = sale.property_type or prop.property_type or "Unknown"
            ptype = ptype.strip().upper() or "Unknown"
            type_data[ptype].append(sale.price_numeric)

            street = _extract_street(prop.address)
            street_data[street].append(sale.price_numeric)

            if prop.postcode:
                pc_data[prop.postcode].append(sale.price_numeric)

            if prop.bedrooms is not None:
                bed_data[prop.bedrooms].append(sale.price_numeric)

        if has_date and not has_price:
            year_counts[int(sale.date_sold_iso[:4])] += 1

    price_trends = [
        PriceTrendPoint(
            month=m,
            avg_price=round(statistics.mean(p)),
            median_price=round(statistics.median(p)),
            min_price=min(p),
            max_price=max(p),
            count=len(p),
        )
        for m, p in sorted(monthly.items())
    ]

    property_types = sorted(
        [
            PropertyTypeBreakdown(
                property_type=t, count=len(p),
                avg_price=round(statistics.mean(p)) if p else None,
            )
            for t, p in type_data.items()
        ],
        key=lambda x: x.count, reverse=True,
    )

    street_comparison = sorted(
        [
            StreetComparison(
                street=s, avg_price=round(statistics.mean(p)) if p else None,
                count=len(p),
            )
            for s, p in street_data.items()
        ],
        key=lambda x: x.avg_price or 0, reverse=True,
    )

    bedroom_distribution = sorted(
        [
            BedroomDistribution(
                bedrooms=b, count=len(p),
                avg_price=round(statistics.mean(p)) if p else None,
            )
            for b, p in bed_data.items()
        ],
        key=lambda x: x.bedrooms,
    )

    sales_volume = [
        SalesVolumePoint(year=y, count=c)
        for y, c in sorted(year_counts.items())
    ]

    postcode_comparison = sorted(
        [
            PostcodeComparison(
                postcode=pc, avg_price=round(statistics.mean(p)) if p else None,
                count=len(p),
            )
            for pc, p in pc_data.items()
        ],
        key=lambda x: x.avg_price or 0, reverse=True,
    )

    postcode_clean = postcode.upper().replace("-", "").replace(" ", "")
    return PostcodeAnalytics(
        postcode=postcode_clean,
        price_trends=price_trends,
        property_types=property_types,
        street_comparison=street_comparison,
        postcode_comparison=postcode_comparison,
        bedroom_distribution=bedroom_distribution,
        sales_volume=sales_volume,
    )
