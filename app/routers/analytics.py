import math
import re
import statistics
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..feature_parser import parse_all_features
from ..models import Property, Sale
from ..schemas import (
    AnnualMedian,
    BedroomDistribution,
    GrowthForecastPoint,
    GrowthLeaderboardEntry,
    GrowthPeriodMetric,
    HousingInsightsResponse,
    InsightsTimeSeriesPoint,
    InvestmentDeal,
    KPIData,
    MarketOverview,
    PostcodeAnalytics,
    PostcodeComparison,
    PostcodeGrowthResponse,
    PostcodeHeatmapPoint,
    PriceHistogramBucket,
    PriceRangeBucket,
    PriceTrendPoint,
    PropertyTypeBreakdown,
    RecentSale,
    SalesVolumePoint,
    ScatterPoint,
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

    # 10. Most recent 50 sales
    recent_rows = (
        db.query(Sale, Property)
        .join(Property, Sale.property_id == Property.id)
        .filter(Sale.date_sold_iso.isnot(None), Sale.price_numeric.isnot(None))
        .order_by(Sale.date_sold_iso.desc())
        .limit(50)
        .all()
    )
    recent_sales = [
        RecentSale(
            property_id=prop.id,
            address=prop.address,
            postcode=prop.postcode,
            price=sale.price_numeric,
            date_sold=sale.date_sold_iso,
            property_type=(sale.property_type or prop.property_type or "Unknown").strip(),
            bedrooms=prop.bedrooms,
        )
        for sale, prop in recent_rows
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
        recent_sales=recent_sales,
    )


@router.get("/housing-insights", response_model=HousingInsightsResponse)
def get_housing_insights(
    db: Session = Depends(get_db),
    property_type: Optional[str] = None,
    min_bedrooms: Optional[int] = None,
    max_bedrooms: Optional[int] = None,
    min_bathrooms: Optional[int] = None,
    max_bathrooms: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    postcode_prefix: Optional[str] = None,
    tenure: Optional[str] = None,
    epc_rating: Optional[str] = None,
    has_garden: Optional[bool] = None,
    has_parking: Optional[bool] = None,
    chain_free: Optional[bool] = None,
    has_listing: Optional[bool] = None,
):
    """Investment-focused analytics dashboard with histogram, time series,
    scatter, heatmap, KPIs, and investment deals."""

    # --- 1. Build base query with SQL-level filters ---
    q = db.query(Sale, Property).join(Property, Sale.property_id == Property.id)

    if postcode_prefix:
        prefix = postcode_prefix.upper().strip()
        q = q.filter(Property.postcode.isnot(None))
        q = q.filter(func.upper(Property.postcode).like(f"{prefix}%"))
    if property_type:
        ptype = property_type.strip().upper()
        q = q.filter(
            func.upper(func.coalesce(Sale.property_type, Property.property_type))
            == ptype
        )
    if min_bedrooms is not None:
        q = q.filter(Property.bedrooms >= min_bedrooms)
    if max_bedrooms is not None:
        q = q.filter(Property.bedrooms <= max_bedrooms)
    if min_bathrooms is not None:
        q = q.filter(Property.bathrooms >= min_bathrooms)
    if max_bathrooms is not None:
        q = q.filter(Property.bathrooms <= max_bathrooms)
    if min_price is not None:
        q = q.filter(Sale.price_numeric >= min_price)
    if max_price is not None:
        q = q.filter(Sale.price_numeric <= max_price)
    if tenure:
        q = q.filter(func.upper(Sale.tenure) == tenure.upper().strip())
    if has_listing is not None:
        if has_listing:
            q = q.filter(Property.listing_status == "for_sale")
        else:
            q = q.filter(
                (Property.listing_status.is_(None)) | (Property.listing_status != "for_sale")
            )

    rows = q.all()

    # --- 2. Feature filters (only when active) ---
    feature_filtering = epc_rating is not None or has_garden is not None or has_parking is not None or chain_free is not None
    if feature_filtering:
        allowed_prop_ids: set[int] = set()
        # Cache parsed features per property to avoid re-parsing
        prop_features_cache: dict[int, dict] = {}
        prop_ids_in_rows = {prop.id for _sale, prop in rows}

        # Load extra_features for relevant properties
        prop_rows = (
            db.query(Property.id, Property.extra_features)
            .filter(Property.id.in_(prop_ids_in_rows))
            .all()
        )
        for pid, raw_features in prop_rows:
            parsed = parse_all_features(raw_features)
            prop_features_cache[pid] = parsed

            matches = True
            if epc_rating and parsed.get("epc_rating") != epc_rating.upper():
                matches = False
            if has_garden is not None:
                has = parsed.get("garden") is not None
                if has != has_garden:
                    matches = False
            if has_parking is not None:
                has = parsed.get("parking") is not None
                if has != has_parking:
                    matches = False
            if chain_free is not None:
                is_cf = parsed.get("chain_free") is True
                if is_cf != chain_free:
                    matches = False

            if matches:
                allowed_prop_ids.add(pid)

        rows = [(sale, prop) for sale, prop in rows if prop.id in allowed_prop_ids]

    # --- 3. Single-pass aggregation ---
    all_prices: list[int] = []
    monthly_prices: dict[str, list[int]] = defaultdict(list)
    scatter_points: list[ScatterPoint] = []
    postcode_prices: dict[str, list[int]] = defaultdict(list)
    postcode_dates: dict[str, list[tuple[str, int]]] = defaultdict(list)
    bedroom_prices: dict[int, list[int]] = defaultdict(list)
    yearly_counts: dict[int, int] = defaultdict(int)
    property_ids: set[int] = set()
    # For investment deals: track latest sale per property
    latest_sale_per_prop: dict[int, tuple] = {}  # prop_id -> (sale, prop)

    for sale, prop in rows:
        price = sale.price_numeric
        date_iso = sale.date_sold_iso
        has_price = price is not None
        has_date = date_iso is not None

        property_ids.add(prop.id)

        if has_price:
            all_prices.append(price)

            # Scatter data (cap at 2000)
            if len(scatter_points) < 2000 and prop.bedrooms is not None:
                ptype = sale.property_type or prop.property_type or "Unknown"
                scatter_points.append(ScatterPoint(
                    bedrooms=prop.bedrooms,
                    price=price,
                    postcode=prop.postcode or "Unknown",
                    property_type=ptype.strip(),
                ))

            # Bedroom prices
            if prop.bedrooms is not None:
                bedroom_prices[prop.bedrooms].append(price)

            # Postcode prices
            if prop.postcode:
                postcode_prices[prop.postcode].append(price)

            if has_date:
                monthly_prices[date_iso[:7]].append(price)
                year = int(date_iso[:4])
                yearly_counts[year] += 1
                postcode_dates[prop.postcode or "Unknown"].append((date_iso, price))

                # Track latest sale per property for deals
                existing = latest_sale_per_prop.get(prop.id)
                if existing is None or date_iso > (existing[0].date_sold_iso or ""):
                    latest_sale_per_prop[prop.id] = (sale, prop)

        elif has_date:
            year = int(date_iso[:4])
            yearly_counts[year] += 1

    # --- Price histogram (20 buckets) ---
    price_histogram: list[PriceHistogramBucket] = []
    if all_prices:
        p_min, p_max = min(all_prices), max(all_prices)
        if p_min == p_max:
            p_max = p_min + 1
        bucket_size = math.ceil((p_max - p_min) / 20)
        bucket_counts: dict[int, int] = defaultdict(int)
        for p in all_prices:
            idx = min((p - p_min) // bucket_size, 19)
            bucket_counts[idx] += 1
        for i in range(20):
            lo = p_min + i * bucket_size
            hi = lo + bucket_size
            if bucket_counts[i] > 0 or i == 0 or i == 19:
                price_histogram.append(PriceHistogramBucket(
                    range_label=f"£{lo:,}-£{hi:,}",
                    min_price=lo,
                    max_price=hi,
                    count=bucket_counts[i],
                ))

    # --- Time series (monthly) ---
    time_series = [
        InsightsTimeSeriesPoint(
            month=m,
            median_price=round(statistics.median(prices)),
            sales_count=len(prices),
        )
        for m, prices in sorted(monthly_prices.items())
    ]

    # --- Postcode heatmap with growth ---
    postcode_heatmap: list[PostcodeHeatmapPoint] = []
    for pc, prices in postcode_prices.items():
        avg_p = statistics.mean(prices)
        growth = None
        dates_prices = postcode_dates.get(pc, [])
        if len(dates_prices) >= 2:
            sorted_dp = sorted(dates_prices, key=lambda x: x[0])
            # Compare first year avg to last year avg
            first_year = sorted_dp[0][0][:4]
            last_year = sorted_dp[-1][0][:4]
            if first_year != last_year:
                first_prices = [p for d, p in sorted_dp if d[:4] == first_year]
                last_prices = [p for d, p in sorted_dp if d[:4] == last_year]
                if first_prices and last_prices:
                    first_avg = statistics.mean(first_prices)
                    last_avg = statistics.mean(last_prices)
                    if first_avg > 0:
                        years_span = int(last_year) - int(first_year)
                        total_growth = (last_avg - first_avg) / first_avg
                        growth = round(
                            (total_growth / years_span) * 100, 1
                        ) if years_span > 0 else None

        postcode_heatmap.append(PostcodeHeatmapPoint(
            postcode=pc,
            avg_price=round(avg_p),
            count=len(prices),
            growth_pct=growth,
        ))
    postcode_heatmap.sort(key=lambda x: x.count, reverse=True)

    # --- KPIs ---
    # Appreciation rate: overall annualized price growth
    appreciation_rate = None
    if time_series and len(time_series) >= 2:
        first_price = time_series[0].median_price
        last_price = time_series[-1].median_price
        if first_price and last_price and first_price > 0:
            months_span = len(time_series)
            years_span = months_span / 12
            if years_span > 0:
                total_growth = (last_price - first_price) / first_price
                appreciation_rate = round(
                    (total_growth / years_span) * 100, 1
                )

    # Price per bedroom
    price_per_bedroom = None
    bed_total_price = 0
    bed_total_beds = 0
    for beds, prices in bedroom_prices.items():
        if beds > 0:
            bed_total_price += sum(prices)
            bed_total_beds += beds * len(prices)
    if bed_total_beds > 0:
        price_per_bedroom = round(bed_total_price / bed_total_beds)

    # Market velocity: compare last year's sales count to previous year
    market_velocity_pct = None
    market_velocity_direction = None
    sorted_years = sorted(yearly_counts.keys())
    if len(sorted_years) >= 2:
        last_yr = sorted_years[-1]
        prev_yr = sorted_years[-2]
        prev_count = yearly_counts[prev_yr]
        curr_count = yearly_counts[last_yr]
        if prev_count > 0:
            market_velocity_pct = round(
                ((curr_count - prev_count) / prev_count) * 100, 1
            )
            market_velocity_direction = "accelerating" if market_velocity_pct > 0 else "decelerating"

    # Price volatility (coefficient of variation)
    price_volatility_pct = None
    if len(all_prices) >= 2:
        mean_p = statistics.mean(all_prices)
        if mean_p > 0:
            stdev_p = statistics.stdev(all_prices)
            price_volatility_pct = round((stdev_p / mean_p) * 100, 1)

    kpis = KPIData(
        appreciation_rate=appreciation_rate,
        price_per_bedroom=price_per_bedroom,
        market_velocity_pct=market_velocity_pct,
        market_velocity_direction=market_velocity_direction,
        price_volatility_pct=price_volatility_pct,
        total_sales=len(all_prices),
        total_properties=len(property_ids),
        median_price=round(statistics.median(all_prices)) if all_prices else None,
    )

    # --- Investment deals ---
    # Properties whose latest sale is >5% below their postcode average
    investment_deals: list[InvestmentDeal] = []
    for _prop_id, (sale, prop) in latest_sale_per_prop.items():
        if not sale.price_numeric or not prop.postcode:
            continue
        pc_prices = postcode_prices.get(prop.postcode, [])
        if len(pc_prices) < 2:
            continue
        pc_avg = statistics.mean(pc_prices)
        if pc_avg <= 0:
            continue
        discount_pct = ((pc_avg - sale.price_numeric) / pc_avg) * 100
        if discount_pct > 5:
            risk = "Low" if discount_pct <= 15 else "Medium" if discount_pct <= 25 else "High"
            investment_deals.append(InvestmentDeal(
                property_id=prop.id,
                address=prop.address,
                postcode=prop.postcode,
                property_type=(sale.property_type or prop.property_type or "Unknown").strip(),
                bedrooms=prop.bedrooms,
                price=sale.price_numeric,
                date_sold=sale.date_sold_iso or sale.date_sold,
                postcode_avg=round(pc_avg),
                value_score=round(discount_pct, 1),
                risk_level=risk,
            ))

    investment_deals.sort(key=lambda x: x.value_score, reverse=True)
    investment_deals = investment_deals[:50]

    # --- Build filters_applied ---
    filters_applied: dict = {}
    if property_type:
        filters_applied["property_type"] = property_type
    if min_bedrooms is not None:
        filters_applied["min_bedrooms"] = min_bedrooms
    if max_bedrooms is not None:
        filters_applied["max_bedrooms"] = max_bedrooms
    if min_bathrooms is not None:
        filters_applied["min_bathrooms"] = min_bathrooms
    if max_bathrooms is not None:
        filters_applied["max_bathrooms"] = max_bathrooms
    if min_price is not None:
        filters_applied["min_price"] = min_price
    if max_price is not None:
        filters_applied["max_price"] = max_price
    if postcode_prefix:
        filters_applied["postcode_prefix"] = postcode_prefix
    if tenure:
        filters_applied["tenure"] = tenure
    if epc_rating:
        filters_applied["epc_rating"] = epc_rating
    if has_garden is not None:
        filters_applied["has_garden"] = has_garden
    if has_parking is not None:
        filters_applied["has_parking"] = has_parking
    if chain_free is not None:
        filters_applied["chain_free"] = chain_free
    if has_listing is not None:
        filters_applied["has_listing"] = has_listing

    return HousingInsightsResponse(
        price_histogram=price_histogram,
        time_series=time_series,
        scatter_data=scatter_points,
        postcode_heatmap=postcode_heatmap,
        kpis=kpis,
        investment_deals=investment_deals,
        filters_applied=filters_applied,
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


# --- Capital Growth & Forecasting ---


def _compute_annual_medians(
    db: Session, postcode: str
) -> list:
    """Get median sale price per year for a postcode."""
    rows = _get_sales_for_postcode(db, postcode)
    yearly: dict[int, list[int]] = defaultdict(list)
    for sale, _prop in rows:
        if sale.price_numeric and sale.date_sold_iso:
            year = int(sale.date_sold_iso[:4])
            yearly[year].append(sale.price_numeric)

    return [
        AnnualMedian(
            year=y,
            median_price=round(statistics.median(prices)),
            sale_count=len(prices),
        )
        for y, prices in sorted(yearly.items())
    ]


def _compute_cagr(start: float, end: float, years: int) -> Optional[float]:
    """Compound Annual Growth Rate as a percentage."""
    if start <= 0 or years <= 0:
        return None
    return round((math.pow(end / start, 1 / years) - 1) * 100, 2)


def _compute_growth_metrics(
    medians: list, periods: list
) -> list:
    """Compute CAGR for each requested period."""
    if not medians:
        return []
    latest_year = medians[-1].year
    results = []
    for period in periods:
        target_year = latest_year - period
        # Find closest year >= target
        start_median = None
        for m in medians:
            if m.year >= target_year:
                start_median = m
                break
        end_median = medians[-1]
        actual_years = end_median.year - start_median.year if start_median else 0
        cagr = None
        if start_median and actual_years > 0:
            cagr = _compute_cagr(
                start_median.median_price, end_median.median_price, actual_years
            )
        results.append(GrowthPeriodMetric(
            period_years=period,
            cagr_pct=cagr,
            start_price=start_median.median_price if start_median else None,
            end_price=end_median.median_price,
        ))
    return results


def _compute_volatility(medians: list) -> Optional[float]:
    """Annual return volatility (std dev of year-over-year % changes)."""
    if len(medians) < 3:
        return None
    returns = []
    for i in range(1, len(medians)):
        prev = medians[i - 1].median_price
        curr = medians[i].median_price
        if prev > 0:
            returns.append((curr - prev) / prev * 100)
    if len(returns) < 2:
        return None
    return round(statistics.stdev(returns), 2)


def _compute_max_drawdown(medians: list) -> Optional[float]:
    """Largest peak-to-trough decline in median prices (percentage)."""
    if len(medians) < 2:
        return None
    peak = medians[0].median_price
    max_dd = 0.0
    for m in medians:
        if m.median_price > peak:
            peak = m.median_price
        if peak > 0:
            dd = (peak - m.median_price) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 2) if max_dd > 0 else None


def _compute_forecast(
    medians: list,
) -> list:
    """Linear forecast with confidence bands. Uses scipy if available."""
    if len(medians) < 3:
        return []
    try:
        from scipy.optimize import curve_fit
    except ImportError:
        return _linear_forecast_fallback(medians)

    import numpy as np

    years = np.array([m.year for m in medians], dtype=float)
    prices = np.array([m.median_price for m in medians], dtype=float)

    # Normalize years for numerical stability
    base_year = years[0]
    x = years - base_year

    def linear(t, a, b):
        return a * t + b

    try:
        popt, _ = curve_fit(linear, x, prices)
        residuals = prices - linear(x, *popt)
        std_residual = float(np.std(residuals))
    except Exception:
        return _linear_forecast_fallback(medians)

    latest_year = int(years[-1])
    forecasts = []
    for horizon in [1, 3, 5]:
        future_x = float(latest_year + horizon - base_year)
        predicted = float(linear(future_x, *popt))
        forecasts.append(GrowthForecastPoint(
            year=latest_year + horizon,
            predicted_price=round(max(predicted, 0)),
            lower_bound=round(max(predicted - std_residual, 0)),
            upper_bound=round(max(predicted + std_residual, 0)),
        ))
    return forecasts


def _linear_forecast_fallback(
    medians: list,
) -> list:
    """Simple linear regression fallback without scipy."""
    n = len(medians)
    if n < 2:
        return []
    years = [m.year for m in medians]
    prices = [m.median_price for m in medians]
    mean_x = statistics.mean(years)
    mean_y = statistics.mean(prices)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(years, prices))
    denominator = sum((x - mean_x) ** 2 for x in years)
    if denominator == 0:
        return []
    slope = numerator / denominator
    intercept = mean_y - slope * mean_x
    residuals = [y - (slope * x + intercept) for x, y in zip(years, prices)]
    std_r = statistics.stdev(residuals) if len(residuals) >= 2 else 0

    latest_year = years[-1]
    forecasts = []
    for horizon in [1, 3, 5]:
        predicted = slope * (latest_year + horizon) + intercept
        forecasts.append(GrowthForecastPoint(
            year=latest_year + horizon,
            predicted_price=round(max(predicted, 0)),
            lower_bound=round(max(predicted - std_r, 0)),
            upper_bound=round(max(predicted + std_r, 0)),
        ))
    return forecasts


@postcode_router.get(
    "/{postcode}/growth",
    response_model=PostcodeGrowthResponse,
)
def get_postcode_growth(
    postcode: str,
    periods: str = Query(default="1,3,5,10", description="Comma-separated year periods"),
    db: Session = Depends(get_db),
):
    """Capital growth metrics and forecast for a postcode."""
    medians = _compute_annual_medians(db, postcode)
    if not medians:
        raise HTTPException(status_code=404, detail="No sale data for this postcode")

    period_list = [int(p.strip()) for p in periods.split(",") if p.strip().isdigit()]
    period_list = [p for p in period_list if 1 <= p <= 30][:10]  # Cap at 10 periods, max 30yr
    metrics = _compute_growth_metrics(medians, period_list)
    volatility = _compute_volatility(medians)
    max_drawdown = _compute_max_drawdown(medians)
    forecast = _compute_forecast(medians)

    return PostcodeGrowthResponse(
        postcode=postcode.upper().strip(),
        metrics=metrics,
        volatility_pct=volatility,
        max_drawdown_pct=max_drawdown,
        forecast=forecast,
        annual_medians=medians,
        data_years=medians[-1].year - medians[0].year if len(medians) >= 2 else 0,
    )


@router.get(
    "/growth-leaderboard",
    response_model=list[GrowthLeaderboardEntry],
)
def get_growth_leaderboard(
    limit: int = Query(default=20, le=100),
    period: int = Query(default=5, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Top postcodes by CAGR over the specified period."""
    # Get distinct postcodes with sales — cap at 500 to bound computation
    postcodes = [
        row[0]
        for row in db.query(func.distinct(Property.postcode))
        .filter(Property.postcode.isnot(None))
        .limit(500)
        .all()
    ]

    entries = []
    for pc in postcodes:
        medians = _compute_annual_medians(db, pc)
        if len(medians) < 2:
            continue
        data_years = medians[-1].year - medians[0].year
        if data_years < min(period, 2):
            continue

        metrics = _compute_growth_metrics(medians, [period])
        if metrics and metrics[0].cagr_pct is not None:
            total_sales = sum(m.sale_count for m in medians)
            entries.append(GrowthLeaderboardEntry(
                postcode=pc,
                cagr_pct=metrics[0].cagr_pct,
                data_years=data_years,
                latest_median=medians[-1].median_price,
                sale_count=total_sales,
            ))

    entries.sort(key=lambda x: x.cagr_pct, reverse=True)
    return entries[:limit]
