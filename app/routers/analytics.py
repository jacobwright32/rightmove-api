import math
import re
import statistics
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, literal_column, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..feature_parser import parse_all_features
from ..models import Property, Sale
from ..schemas import (
    AnnualMedian,
    BedroomDistribution,
    CurrentListing,
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

# --- Simple in-memory TTL cache ---
_cache = {}  # type: dict[str, tuple[float, object]]


def _cache_get(key, ttl_seconds):
    """Return cached value if still valid, else None."""
    entry = _cache.get(key)
    if entry and (time.monotonic() - entry[0]) < ttl_seconds:
        return entry[1]
    return None


def _cache_set(key, value):
    _cache[key] = (time.monotonic(), value)


@router.get("/market-overview", response_model=MarketOverview)
def get_market_overview(db: Session = Depends(get_db)):
    """Database-wide aggregated statistics across all properties and sales."""
    cached = _cache_get("market_overview", 1800)  # 30 min TTL
    if cached is not None:
        return cached
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

    # 3. Average and median price_numeric across all sales (SQL aggregation)
    price_stats = (
        db.query(func.avg(Sale.price_numeric), func.count(Sale.price_numeric))
        .filter(Sale.price_numeric.isnot(None))
        .one()
    )
    avg_price: Optional[float] = round(price_stats[0]) if price_stats[0] else None
    price_count = price_stats[1] or 0
    # Median via ORDER BY + OFFSET (SQLite has no built-in median)
    median_price: Optional[float] = None
    if price_count > 0:
        offset = price_count // 2
        median_row = (
            db.query(Sale.price_numeric)
            .filter(Sale.price_numeric.isnot(None))
            .order_by(Sale.price_numeric)
            .offset(offset)
            .limit(1)
            .one()
        )
        median_price = median_row[0]

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

    # 6. Property type breakdown (SQL GROUP BY)
    ptype_expr = func.upper(
        func.trim(func.coalesce(Sale.property_type, Property.property_type, "Unknown"))
    )
    type_rows = (
        db.query(
            ptype_expr.label("ptype"),
            func.count(Sale.id).label("cnt"),
            func.avg(Sale.price_numeric).label("avg_p"),
        )
        .join(Property, Sale.property_id == Property.id)
        .filter(Sale.price_numeric.isnot(None))
        .group_by(ptype_expr)
        .order_by(func.count(Sale.id).desc())
        .all()
    )
    property_types = [
        PropertyTypeBreakdown(
            property_type=row.ptype or "Unknown",
            count=row.cnt,
            avg_price=round(row.avg_p) if row.avg_p else None,
        )
        for row in type_rows
    ]

    # 7. Bedroom distribution (SQL GROUP BY)
    bed_rows = (
        db.query(
            Property.bedrooms,
            func.count(Sale.id).label("cnt"),
            func.avg(Sale.price_numeric).label("avg_p"),
        )
        .join(Sale, Sale.property_id == Property.id)
        .filter(Property.bedrooms.isnot(None), Sale.price_numeric.isnot(None))
        .group_by(Property.bedrooms)
        .order_by(Property.bedrooms)
        .all()
    )
    bedroom_distribution = [
        BedroomDistribution(
            bedrooms=row[0],
            count=row[1],
            avg_price=round(row[2]) if row[2] else None,
        )
        for row in bed_rows
    ]

    # 8. Yearly sales volume (SQL GROUP BY)
    year_expr = func.substr(Sale.date_sold_iso, 1, 4)
    year_rows = (
        db.query(year_expr.label("yr"), func.count(Sale.id).label("cnt"))
        .filter(Sale.date_sold_iso.isnot(None))
        .group_by(year_expr)
        .order_by(year_expr)
        .all()
    )
    yearly_trends = [
        SalesVolumePoint(year=int(row.yr), count=row.cnt)
        for row in year_rows
    ]

    # 9. Monthly price trends (SQL GROUP BY — uses avg as proxy for median)
    month_expr = func.substr(Sale.date_sold_iso, 1, 7)
    monthly_rows = (
        db.query(
            month_expr.label("mo"),
            func.avg(Sale.price_numeric).label("avg_p"),
            func.min(Sale.price_numeric).label("min_p"),
            func.max(Sale.price_numeric).label("max_p"),
            func.count(Sale.id).label("cnt"),
        )
        .filter(Sale.date_sold_iso.isnot(None), Sale.price_numeric.isnot(None))
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )
    price_trends = [
        PriceTrendPoint(
            month=row.mo,
            avg_price=round(row.avg_p),
            median_price=round(row.avg_p),  # avg as proxy; per-month median too expensive
            min_price=row.min_p,
            max_price=row.max_p,
            count=row.cnt,
        )
        for row in monthly_rows
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

    result = MarketOverview(
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
    _cache_set("market_overview", result)
    return result


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
    # Cache key based on all filter params
    cache_key = f"insights:{property_type}:{min_bedrooms}:{max_bedrooms}:{min_bathrooms}:{max_bathrooms}:{min_price}:{max_price}:{postcode_prefix}:{tenure}:{epc_rating}:{has_garden}:{has_parking}:{chain_free}:{has_listing}"
    cached = _cache_get(cache_key, 600)  # 10 min TTL
    if cached is not None:
        return cached

    # --- Feature filtering requires Python-side pass (JSON parsing) ---
    feature_filtering = (
        epc_rating is not None or has_garden is not None
        or has_parking is not None or chain_free is not None
    )

    # If feature filtering is active, fall back to loading rows (unavoidable)
    if feature_filtering:
        result = _housing_insights_with_feature_filter(
            db, property_type, min_bedrooms, max_bedrooms,
            min_bathrooms, max_bathrooms, min_price, max_price,
            postcode_prefix, tenure, epc_rating, has_garden,
            has_parking, chain_free, has_listing,
        )
        _cache_set(cache_key, result)
        return result

    # --- SQL-optimized path (no feature filters) ---

    def _apply_filters(q):
        """Apply common SQL filters to a query that already joins Sale+Property."""
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
                    (Property.listing_status.is_(None))
                    | (Property.listing_status != "for_sale")
                )
        return q

    # --- 1. Price histogram: get min/max then bucket in SQL ---
    base_q = db.query(Sale).join(Property, Sale.property_id == Property.id)
    base_q = _apply_filters(base_q)
    price_base = base_q.filter(Sale.price_numeric.isnot(None))

    range_row = (
        price_base.with_entities(
            func.min(Sale.price_numeric),
            func.max(Sale.price_numeric),
            func.count(Sale.price_numeric),
        ).one()
    )
    p_min, p_max, total_with_price = range_row[0], range_row[1], range_row[2]

    price_histogram = []  # type: list[PriceHistogramBucket]
    if p_min is not None and total_with_price > 0:
        if p_min == p_max:
            p_max = p_min + 1
        bucket_size = math.ceil((p_max - p_min) / 20)
        # SQL bucket counting
        bucket_expr = case(
            (func.min(Sale.price_numeric, (Sale.price_numeric - p_min) / bucket_size) > 19,
             literal_column("19")),
            else_=(Sale.price_numeric - p_min) / bucket_size,
        )
        # Simpler: compute in Python from raw SQL grouping
        bucket_idx_expr = func.min(
            literal_column("19"),
            (Sale.price_numeric - p_min) / bucket_size,
        )
        hist_rows = (
            price_base.with_entities(
                ((Sale.price_numeric - p_min) / bucket_size).label("bucket"),
                func.count(Sale.id).label("cnt"),
            )
            .group_by("bucket")
            .all()
        )
        bucket_counts = {}  # type: dict[int, int]
        for row in hist_rows:
            idx = min(int(row.bucket), 19)
            bucket_counts[idx] = bucket_counts.get(idx, 0) + row.cnt
        for i in range(20):
            lo = p_min + i * bucket_size
            hi = lo + bucket_size
            cnt = bucket_counts.get(i, 0)
            if cnt > 0 or i == 0 or i == 19:
                price_histogram.append(PriceHistogramBucket(
                    range_label=f"\u00a3{lo:,}-\u00a3{hi:,}",
                    min_price=lo,
                    max_price=hi,
                    count=cnt,
                ))

    # --- 2. Time series (monthly avg as proxy for median) ---
    month_expr = func.substr(Sale.date_sold_iso, 1, 7)
    ts_q = (
        price_base.filter(Sale.date_sold_iso.isnot(None))
        .with_entities(
            month_expr.label("mo"),
            func.avg(Sale.price_numeric).label("avg_p"),
            func.count(Sale.id).label("cnt"),
        )
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )
    time_series = [
        InsightsTimeSeriesPoint(
            month=row.mo,
            median_price=round(row.avg_p),
            sales_count=row.cnt,
        )
        for row in ts_q
    ]

    # --- 3. Scatter data (select only needed columns, limit 2000) ---
    scatter_q = (
        price_base.filter(Property.bedrooms.isnot(None))
        .with_entities(
            Property.bedrooms,
            Sale.price_numeric,
            func.coalesce(Property.postcode, "Unknown"),
            func.trim(func.coalesce(Sale.property_type, Property.property_type, "Unknown")),
        )
        .limit(2000)
        .all()
    )
    scatter_points = [
        ScatterPoint(
            bedrooms=row[0], price=row[1],
            postcode=row[2], property_type=row[3],
        )
        for row in scatter_q
    ]

    # --- 4. Postcode heatmap with growth ---
    pc_stats_q = (
        price_base.filter(Property.postcode.isnot(None))
        .with_entities(
            Property.postcode,
            func.avg(Sale.price_numeric).label("avg_p"),
            func.count(Sale.id).label("cnt"),
        )
        .group_by(Property.postcode)
        .order_by(func.count(Sale.id).desc())
        .all()
    )
    # For growth: per-postcode, per-year averages
    year_expr = func.substr(Sale.date_sold_iso, 1, 4)
    pc_year_q = (
        price_base.filter(
            Property.postcode.isnot(None), Sale.date_sold_iso.isnot(None)
        )
        .with_entities(
            Property.postcode,
            year_expr.label("yr"),
            func.avg(Sale.price_numeric).label("avg_p"),
        )
        .group_by(Property.postcode, year_expr)
        .all()
    )
    # Build lookup: postcode -> {year: avg_price}
    pc_year_map = defaultdict(dict)  # type: dict[str, dict[str, float]]
    for row in pc_year_q:
        pc_year_map[row[0]][row[1]] = float(row[2])

    postcode_heatmap = []  # type: list[PostcodeHeatmapPoint]
    for row in pc_stats_q:
        pc = row[0]
        growth = None
        year_data = pc_year_map.get(pc, {})
        if len(year_data) >= 2:
            sorted_yrs = sorted(year_data.keys())
            first_year, last_year = sorted_yrs[0], sorted_yrs[-1]
            if first_year != last_year:
                first_avg = year_data[first_year]
                last_avg = year_data[last_year]
                if first_avg > 0:
                    years_span = int(last_year) - int(first_year)
                    total_growth = (last_avg - first_avg) / first_avg
                    growth = round((total_growth / years_span) * 100, 1) if years_span > 0 else None
        postcode_heatmap.append(PostcodeHeatmapPoint(
            postcode=pc,
            avg_price=round(row[1]),
            count=row[2],
            growth_pct=growth,
        ))

    # --- 5. KPIs (targeted aggregate queries) ---
    # Total sales and properties
    kpi_counts = (
        base_q.with_entities(
            func.count(Sale.id),
            func.count(func.distinct(Property.id)),
        ).one()
    )
    total_sales_kpi = kpi_counts[0]
    total_properties_kpi = kpi_counts[1]

    # Median price via offset
    kpi_price_stats = (
        price_base.with_entities(
            func.avg(Sale.price_numeric),
            func.count(Sale.price_numeric),
        ).one()
    )
    kpi_median = None
    kpi_price_count = kpi_price_stats[1] or 0
    if kpi_price_count > 0:
        offset = kpi_price_count // 2
        kpi_median_row = (
            price_base.with_entities(Sale.price_numeric)
            .order_by(Sale.price_numeric)
            .offset(offset).limit(1).one()
        )
        kpi_median = kpi_median_row[0]

    # Price volatility (stdev/mean via SQL)
    price_volatility_pct = None
    if kpi_price_count >= 2 and kpi_price_stats[0] and kpi_price_stats[0] > 0:
        # SQLite doesn't have STDEV, compute sum-of-squares
        mean_p = float(kpi_price_stats[0])
        sum_sq = (
            price_base.with_entities(
                func.sum((Sale.price_numeric - mean_p) * (Sale.price_numeric - mean_p))
            ).scalar()
        )
        if sum_sq is not None:
            stdev_p = math.sqrt(sum_sq / (kpi_price_count - 1))
            price_volatility_pct = round((stdev_p / mean_p) * 100, 1)

    # Appreciation rate from time series
    appreciation_rate = None
    if len(time_series) >= 2:
        first_price = time_series[0].median_price
        last_price = time_series[-1].median_price
        if first_price and last_price and first_price > 0:
            months_span = len(time_series)
            years_span = months_span / 12
            if years_span > 0:
                total_growth = (last_price - first_price) / first_price
                appreciation_rate = round((total_growth / years_span) * 100, 1)

    # Price per bedroom
    ppb_row = (
        price_base.filter(Property.bedrooms.isnot(None), Property.bedrooms > 0)
        .with_entities(
            func.sum(Sale.price_numeric),
            func.sum(Property.bedrooms),
        ).one()
    )
    price_per_bedroom = None
    if ppb_row[1] and ppb_row[1] > 0:
        price_per_bedroom = round(ppb_row[0] / ppb_row[1])

    # Market velocity
    year_vol_q = (
        base_q.filter(Sale.date_sold_iso.isnot(None))
        .with_entities(
            func.substr(Sale.date_sold_iso, 1, 4).label("yr"),
            func.count(Sale.id).label("cnt"),
        )
        .group_by("yr")
        .order_by("yr")
        .all()
    )
    market_velocity_pct = None
    market_velocity_direction = None
    if len(year_vol_q) >= 2:
        prev_count = year_vol_q[-2].cnt
        curr_count = year_vol_q[-1].cnt
        if prev_count > 0:
            market_velocity_pct = round(
                ((curr_count - prev_count) / prev_count) * 100, 1
            )
            market_velocity_direction = "accelerating" if market_velocity_pct > 0 else "decelerating"

    kpis = KPIData(
        appreciation_rate=appreciation_rate,
        price_per_bedroom=price_per_bedroom,
        market_velocity_pct=market_velocity_pct,
        market_velocity_direction=market_velocity_direction,
        price_volatility_pct=price_volatility_pct,
        total_sales=total_sales_kpi,
        total_properties=total_properties_kpi,
        median_price=kpi_median,
    )

    # --- 6. Investment deals (latest sale per property vs postcode avg) ---
    # Subquery: latest sale per property (within filters)
    latest_sub = (
        base_q.filter(
            Sale.price_numeric.isnot(None),
            Sale.date_sold_iso.isnot(None),
            Property.postcode.isnot(None),
        )
        .with_entities(
            Sale.property_id,
            func.max(Sale.date_sold_iso).label("max_date"),
        )
        .group_by(Sale.property_id)
        .subquery()
    )
    deal_rows = (
        db.query(
            Sale.property_id,
            Sale.price_numeric,
            Sale.date_sold_iso,
            Sale.date_sold,
            func.trim(func.coalesce(Sale.property_type, Property.property_type, "Unknown")).label("ptype"),
            Property.address,
            Property.postcode,
            Property.bedrooms,
        )
        .join(Property, Sale.property_id == Property.id)
        .join(
            latest_sub,
            (Sale.property_id == latest_sub.c.property_id)
            & (Sale.date_sold_iso == latest_sub.c.max_date),
        )
        .all()
    )
    # Build postcode avg lookup from heatmap data
    pc_avg_map = {h.postcode: h.avg_price for h in postcode_heatmap if h.count >= 2}

    investment_deals = []  # type: list[InvestmentDeal]
    for row in deal_rows:
        pc_avg = pc_avg_map.get(row.postcode)
        if not pc_avg or pc_avg <= 0:
            continue
        discount_pct = ((pc_avg - row.price_numeric) / pc_avg) * 100
        if discount_pct > 5:
            risk = "Low" if discount_pct <= 15 else "Medium" if discount_pct <= 25 else "High"
            investment_deals.append(InvestmentDeal(
                property_id=row.property_id,
                address=row.address,
                postcode=row.postcode,
                property_type=row.ptype,
                bedrooms=row.bedrooms,
                price=row.price_numeric,
                date_sold=row.date_sold_iso or row.date_sold,
                postcode_avg=round(pc_avg),
                value_score=round(discount_pct, 1),
                risk_level=risk,
            ))
    investment_deals.sort(key=lambda x: x.value_score, reverse=True)
    investment_deals = investment_deals[:50]

    # --- 7. Current for-sale listings ---
    lq = db.query(Property).filter(Property.listing_status == "for_sale")
    if postcode_prefix:
        prefix = postcode_prefix.upper().strip()
        lq = lq.filter(Property.postcode.isnot(None))
        lq = lq.filter(func.upper(Property.postcode).like(f"{prefix}%"))
    if property_type:
        ptype = property_type.strip().upper()
        lq = lq.filter(func.upper(Property.property_type) == ptype)
    if min_bedrooms is not None:
        lq = lq.filter(Property.bedrooms >= min_bedrooms)
    if max_bedrooms is not None:
        lq = lq.filter(Property.bedrooms <= max_bedrooms)
    if min_bathrooms is not None:
        lq = lq.filter(Property.bathrooms >= min_bathrooms)
    if max_bathrooms is not None:
        lq = lq.filter(Property.bathrooms <= max_bathrooms)
    if min_price is not None:
        lq = lq.filter(Property.listing_price >= min_price)
    if max_price is not None:
        lq = lq.filter(Property.listing_price <= max_price)

    listing_props = lq.all()
    current_listings = [
        CurrentListing(
            property_id=p.id,
            address=p.address,
            postcode=p.postcode,
            property_type=(p.property_type or "Unknown").strip(),
            bedrooms=p.bedrooms,
            bathrooms=p.bathrooms,
            listing_price=p.listing_price,
            listing_price_display=p.listing_price_display,
            listing_url=p.listing_url,
            listing_checked_at=p.listing_checked_at,
        )
        for p in listing_props
    ]

    # Include listing-only properties in KPI total
    listing_prop_count = lq.filter(
        ~Property.id.in_(
            db.query(func.distinct(Sale.property_id))
        )
    ).count()
    kpis.total_properties += listing_prop_count

    # --- Build filters_applied ---
    filters_applied = _build_filters_applied(
        property_type, min_bedrooms, max_bedrooms, min_bathrooms,
        max_bathrooms, min_price, max_price, postcode_prefix,
        tenure, epc_rating, has_garden, has_parking, chain_free, has_listing,
    )

    result = HousingInsightsResponse(
        price_histogram=price_histogram,
        time_series=time_series,
        scatter_data=scatter_points,
        postcode_heatmap=postcode_heatmap,
        kpis=kpis,
        investment_deals=investment_deals,
        current_listings=current_listings,
        filters_applied=filters_applied,
    )
    _cache_set(cache_key, result)
    return result


def _build_filters_applied(
    property_type, min_bedrooms, max_bedrooms, min_bathrooms,
    max_bathrooms, min_price, max_price, postcode_prefix,
    tenure, epc_rating, has_garden, has_parking, chain_free, has_listing,
):
    """Build the filters_applied dict from parameters."""
    filters_applied = {}  # type: dict
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
    return filters_applied


def _housing_insights_with_feature_filter(
    db, property_type, min_bedrooms, max_bedrooms,
    min_bathrooms, max_bathrooms, min_price, max_price,
    postcode_prefix, tenure, epc_rating, has_garden,
    has_parking, chain_free, has_listing,
):
    """Fallback path for when feature filters (garden/parking/chain_free/epc)
    are active. These require Python-side JSON parsing so we must load rows."""

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

    # Feature filtering
    allowed_prop_ids = set()  # type: set[int]
    prop_ids_in_rows = {prop.id for _sale, prop in rows}
    prop_rows = (
        db.query(Property.id, Property.extra_features)
        .filter(Property.id.in_(prop_ids_in_rows))
        .all()
    )
    for pid, raw_features in prop_rows:
        parsed = parse_all_features(raw_features)
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

    # Single-pass aggregation (original logic, kept for feature-filter path)
    all_prices = []  # type: list[int]
    monthly_prices = defaultdict(list)  # type: dict[str, list[int]]
    scatter_points = []  # type: list[ScatterPoint]
    postcode_prices = defaultdict(list)  # type: dict[str, list[int]]
    postcode_dates = defaultdict(list)  # type: dict[str, list[tuple[str, int]]]
    bedroom_prices = defaultdict(list)  # type: dict[int, list[int]]
    yearly_counts = defaultdict(int)  # type: dict[int, int]
    property_ids = set()  # type: set[int]
    latest_sale_per_prop = {}  # type: dict[int, tuple]

    for sale, prop in rows:
        price = sale.price_numeric
        date_iso = sale.date_sold_iso
        has_price = price is not None
        has_date = date_iso is not None
        property_ids.add(prop.id)

        if has_price:
            all_prices.append(price)
            if len(scatter_points) < 2000 and prop.bedrooms is not None:
                ptype = sale.property_type or prop.property_type or "Unknown"
                scatter_points.append(ScatterPoint(
                    bedrooms=prop.bedrooms, price=price,
                    postcode=prop.postcode or "Unknown",
                    property_type=ptype.strip(),
                ))
            if prop.bedrooms is not None:
                bedroom_prices[prop.bedrooms].append(price)
            if prop.postcode:
                postcode_prices[prop.postcode].append(price)
            if has_date:
                monthly_prices[date_iso[:7]].append(price)
                year = int(date_iso[:4])
                yearly_counts[year] += 1
                postcode_dates[prop.postcode or "Unknown"].append((date_iso, price))
                existing = latest_sale_per_prop.get(prop.id)
                if existing is None or date_iso > (existing[0].date_sold_iso or ""):
                    latest_sale_per_prop[prop.id] = (sale, prop)
        elif has_date:
            yearly_counts[int(date_iso[:4])] += 1

    # Histogram
    price_histogram = []  # type: list[PriceHistogramBucket]
    if all_prices:
        p_min, p_max = min(all_prices), max(all_prices)
        if p_min == p_max:
            p_max = p_min + 1
        bucket_size = math.ceil((p_max - p_min) / 20)
        bucket_counts = defaultdict(int)  # type: dict[int, int]
        for p in all_prices:
            idx = min((p - p_min) // bucket_size, 19)
            bucket_counts[idx] += 1
        for i in range(20):
            lo = p_min + i * bucket_size
            hi = lo + bucket_size
            if bucket_counts[i] > 0 or i == 0 or i == 19:
                price_histogram.append(PriceHistogramBucket(
                    range_label=f"\u00a3{lo:,}-\u00a3{hi:,}",
                    min_price=lo, max_price=hi, count=bucket_counts[i],
                ))

    time_series = [
        InsightsTimeSeriesPoint(
            month=m, median_price=round(statistics.median(prices)),
            sales_count=len(prices),
        )
        for m, prices in sorted(monthly_prices.items())
    ]

    postcode_heatmap = []  # type: list[PostcodeHeatmapPoint]
    for pc, prices in postcode_prices.items():
        avg_p = statistics.mean(prices)
        growth = None
        dates_prices = postcode_dates.get(pc, [])
        if len(dates_prices) >= 2:
            sorted_dp = sorted(dates_prices, key=lambda x: x[0])
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
            postcode=pc, avg_price=round(avg_p),
            count=len(prices), growth_pct=growth,
        ))
    postcode_heatmap.sort(key=lambda x: x.count, reverse=True)

    # KPIs
    appreciation_rate = None
    if len(time_series) >= 2:
        fp, lp = time_series[0].median_price, time_series[-1].median_price
        if fp and lp and fp > 0:
            ys = len(time_series) / 12
            if ys > 0:
                appreciation_rate = round(((lp - fp) / fp / ys) * 100, 1)

    price_per_bedroom = None
    btp, btb = 0, 0
    for beds, prices in bedroom_prices.items():
        if beds > 0:
            btp += sum(prices)
            btb += beds * len(prices)
    if btb > 0:
        price_per_bedroom = round(btp / btb)

    market_velocity_pct = None
    market_velocity_direction = None
    sorted_years = sorted(yearly_counts.keys())
    if len(sorted_years) >= 2:
        prev_c, curr_c = yearly_counts[sorted_years[-2]], yearly_counts[sorted_years[-1]]
        if prev_c > 0:
            market_velocity_pct = round(((curr_c - prev_c) / prev_c) * 100, 1)
            market_velocity_direction = "accelerating" if market_velocity_pct > 0 else "decelerating"

    price_volatility_pct = None
    if len(all_prices) >= 2:
        mean_p = statistics.mean(all_prices)
        if mean_p > 0:
            price_volatility_pct = round((statistics.stdev(all_prices) / mean_p) * 100, 1)

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

    # Investment deals
    investment_deals = []  # type: list[InvestmentDeal]
    for _pid, (sale, prop) in latest_sale_per_prop.items():
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
                property_id=prop.id, address=prop.address,
                postcode=prop.postcode,
                property_type=(sale.property_type or prop.property_type or "Unknown").strip(),
                bedrooms=prop.bedrooms, price=sale.price_numeric,
                date_sold=sale.date_sold_iso or sale.date_sold,
                postcode_avg=round(pc_avg),
                value_score=round(discount_pct, 1), risk_level=risk,
            ))
    investment_deals.sort(key=lambda x: x.value_score, reverse=True)
    investment_deals = investment_deals[:50]

    # Listings
    lq = db.query(Property).filter(Property.listing_status == "for_sale")
    if postcode_prefix:
        prefix = postcode_prefix.upper().strip()
        lq = lq.filter(Property.postcode.isnot(None))
        lq = lq.filter(func.upper(Property.postcode).like(f"{prefix}%"))
    if property_type:
        ptype = property_type.strip().upper()
        lq = lq.filter(func.upper(Property.property_type) == ptype)
    if min_bedrooms is not None:
        lq = lq.filter(Property.bedrooms >= min_bedrooms)
    if max_bedrooms is not None:
        lq = lq.filter(Property.bedrooms <= max_bedrooms)
    if min_bathrooms is not None:
        lq = lq.filter(Property.bathrooms >= min_bathrooms)
    if max_bathrooms is not None:
        lq = lq.filter(Property.bathrooms <= max_bathrooms)
    if min_price is not None:
        lq = lq.filter(Property.listing_price >= min_price)
    if max_price is not None:
        lq = lq.filter(Property.listing_price <= max_price)

    listing_props = lq.all()
    current_listings = [
        CurrentListing(
            property_id=p.id, address=p.address, postcode=p.postcode,
            property_type=(p.property_type or "Unknown").strip(),
            bedrooms=p.bedrooms, bathrooms=p.bathrooms,
            listing_price=p.listing_price,
            listing_price_display=p.listing_price_display,
            listing_url=p.listing_url,
            listing_checked_at=p.listing_checked_at,
        )
        for p in listing_props
    ]

    listing_only_ids = {p.id for p in listing_props} - property_ids
    kpis.total_properties += len(listing_only_ids)

    filters_applied = _build_filters_applied(
        property_type, min_bedrooms, max_bedrooms, min_bathrooms,
        max_bathrooms, min_price, max_price, postcode_prefix,
        tenure, epc_rating, has_garden, has_parking, chain_free, has_listing,
    )

    return HousingInsightsResponse(
        price_histogram=price_histogram, time_series=time_series,
        scatter_data=scatter_points, postcode_heatmap=postcode_heatmap,
        kpis=kpis, investment_deals=investment_deals,
        current_listings=current_listings, filters_applied=filters_applied,
    )


# --- Postcode-specific analytics ---

postcode_router = APIRouter(prefix="/analytics/postcode", tags=["analytics"])


def _get_sales_for_postcode(db: Session, postcode: str):
    """Get all sales joined with properties for a given postcode."""
    postcode_clean = postcode.upper().replace("-", "").replace(" ", "")
    return (
        db.query(Sale, Property)
        .join(Property, Sale.property_id == Property.id)
        .filter(Property.postcode_clean == postcode_clean)
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
    cache_key = f"leaderboard:{limit}:{period}"
    cached = _cache_get(cache_key, 600)  # 10 min TTL
    if cached is not None:
        return cached
    # Single query: aggregate by postcode + year (replaces ~500 per-postcode queries)
    year_expr = func.substr(Sale.date_sold_iso, 1, 4)
    agg_rows = (
        db.query(
            Property.postcode,
            year_expr.label("yr"),
            func.avg(Sale.price_numeric).label("avg_p"),
            func.count(Sale.id).label("cnt"),
        )
        .join(Sale, Sale.property_id == Property.id)
        .filter(
            Property.postcode.isnot(None),
            Sale.price_numeric.isnot(None),
            Sale.date_sold_iso.isnot(None),
        )
        .group_by(Property.postcode, year_expr)
        .all()
    )

    # Group into postcode -> sorted [(year, avg_price, count)]
    pc_data = defaultdict(list)  # type: dict[str, list[tuple[int, float, int]]]
    for row in agg_rows:
        pc_data[row[0]].append((int(row[1]), float(row[2]), row[3]))

    entries = []
    for pc, year_data in pc_data.items():
        year_data.sort()
        if len(year_data) < 2:
            continue
        first_year = year_data[0][0]
        last_year = year_data[-1][0]
        data_years = last_year - first_year
        if data_years < min(period, 2):
            continue

        # Use avg price per year as proxy for median (matches original behavior closely)
        # Find start year for the requested period
        target_year = last_year - period
        start_entry = None
        for yd in year_data:
            if yd[0] >= target_year:
                start_entry = yd
                break
        if start_entry is None:
            continue

        actual_years = last_year - start_entry[0]
        if actual_years <= 0:
            continue

        cagr = _compute_cagr(start_entry[1], year_data[-1][1], actual_years)
        if cagr is None:
            continue

        total_sales = sum(yd[2] for yd in year_data)
        entries.append(GrowthLeaderboardEntry(
            postcode=pc,
            cagr_pct=cagr,
            data_years=data_years,
            latest_median=round(year_data[-1][1]),
            sale_count=total_sales,
        ))

    entries.sort(key=lambda x: x.cagr_pct, reverse=True)
    result = entries[:limit]
    _cache_set(cache_key, result)
    return result
