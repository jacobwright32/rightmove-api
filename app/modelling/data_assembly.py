"""Data assembly for ML modelling.

Joins Property + Sale + CrimeStats, parses extra_features, and builds
a pandas DataFrame ready for model training or single-row prediction.
"""

import logging
import math
from collections import defaultdict
from typing import Callable, Optional

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..constants import FEATURE_PARSER_KEYS
from ..feature_parser import parse_all_features
from ..models import CrimeStats, Property, Sale

# Type for progress callbacks: (progress_0_to_1, detail_message) -> None
ProgressCallback = Callable[[float, str], None]

logger = logging.getLogger(__name__)

_ASSEMBLY_BATCH_SIZE = 50_000

# ---------------------------------------------------------------------------
# Feature registry — served to the frontend for the feature selection UI
# ---------------------------------------------------------------------------

# Categorical string features (need pd.Categorical dtype)
_CATEGORICAL_FEATURES = {
    "property_type", "epc_rating", "parking", "garden", "heating",
    "lease_type", "furnished", "floor_level", "council_tax_band",
    "flood_risk_level", "tenure",
    "nearest_rail_station", "nearest_tube_station", "nearest_airport", "nearest_port",
    "nearest_primary_school", "nearest_secondary_school",
    "nearest_primary_ofsted", "nearest_secondary_ofsted",
    "nearest_gp_name", "nearest_hospital_name",
    "nearest_supermarket_name", "nearest_supermarket_brand",
    "nearest_pub_name", "nearest_gym_name",
    "nearest_park_name", "nearest_green_space_name",
    # v2 parsed categorical features
    "garden_facing", "property_era", "condition", "kitchen_type",
}

# Numeric features from parsed extras
_NUMERIC_PARSED = {
    "lease_years", "receptions", "sq_ft", "service_charge",
    "ground_rent", "distance_to_station", "acre_plot",
}

# Boolean features from parsed extras (everything in FEATURE_PARSER_KEYS that isn't
# categorical or numeric)
_BOOLEAN_PARSED = set(FEATURE_PARSER_KEYS) - _CATEGORICAL_FEATURES - _NUMERIC_PARSED

# Crime categories from UK Police API — all categories included as ML features
CRIME_CATEGORIES = [
    "anti-social-behaviour",
    "burglary",
    "criminal-damage-and-arson",
    "drugs",
    "other-crime",
    "other-theft",
    "possession-of-weapons",
    "public-order",
    "robbery",
    "shoplifting",
    "theft-from-the-person",
    "vehicle-crime",
    "violence-and-sexual-offences",
]

# Clean column names for crime features (replace hyphens)
CRIME_COL_MAP = {cat: cat.replace("-", "_") for cat in CRIME_CATEGORIES}


def _build_registry() -> list[dict[str, str]]:
    """Build the feature registry for the frontend."""
    registry: list[dict[str, str]] = []

    # Property basics
    registry.append({"name": "bedrooms", "category": "Property Basics", "label": "Bedrooms", "dtype": "numeric"})
    registry.append({"name": "bathrooms", "category": "Property Basics", "label": "Bathrooms", "dtype": "numeric"})
    registry.append({"name": "property_type", "category": "Property Basics", "label": "Property Type", "dtype": "categorical"})

    # EPC
    registry.append({"name": "epc_rating", "category": "EPC", "label": "EPC Rating", "dtype": "categorical"})
    registry.append({"name": "epc_score", "category": "EPC", "label": "EPC Score", "dtype": "numeric"})
    registry.append({"name": "estimated_energy_cost", "category": "EPC", "label": "Energy Cost (£/yr)", "dtype": "numeric"})
    registry.append({"name": "epc_environment_impact", "category": "EPC", "label": "Environment Impact", "dtype": "numeric"})

    # Location
    registry.append({"name": "latitude", "category": "Location", "label": "Latitude", "dtype": "numeric"})
    registry.append({"name": "longitude", "category": "Location", "label": "Longitude", "dtype": "numeric"})
    registry.append({"name": "flood_risk_level", "category": "Location", "label": "Flood Risk Level", "dtype": "categorical"})

    # Transport
    registry.append({"name": "dist_nearest_rail_km", "category": "Transport", "label": "Dist. to Nearest Rail (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_tube_km", "category": "Transport", "label": "Dist. to Nearest Tube (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_bus_km", "category": "Transport", "label": "Dist. to Nearest Bus (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_airport_km", "category": "Transport", "label": "Dist. to Nearest Airport (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_port_km", "category": "Transport", "label": "Dist. to Nearest Port (km)", "dtype": "numeric"})
    registry.append({"name": "bus_stops_within_500m", "category": "Transport", "label": "Bus Stops within 500m", "dtype": "numeric"})
    registry.append({"name": "nearest_rail_station", "category": "Transport", "label": "Nearest Rail Station", "dtype": "categorical"})
    registry.append({"name": "nearest_tube_station", "category": "Transport", "label": "Nearest Tube Station", "dtype": "categorical"})
    registry.append({"name": "nearest_airport", "category": "Transport", "label": "Nearest Airport", "dtype": "categorical"})
    registry.append({"name": "nearest_port", "category": "Transport", "label": "Nearest Port", "dtype": "categorical"})

    # Deprivation (IMD)
    registry.append({"name": "imd_decile", "category": "Deprivation", "label": "IMD Overall Decile", "dtype": "numeric"})
    registry.append({"name": "imd_income_decile", "category": "Deprivation", "label": "Income Decile", "dtype": "numeric"})
    registry.append({"name": "imd_employment_decile", "category": "Deprivation", "label": "Employment Decile", "dtype": "numeric"})
    registry.append({"name": "imd_education_decile", "category": "Deprivation", "label": "Education Decile", "dtype": "numeric"})
    registry.append({"name": "imd_health_decile", "category": "Deprivation", "label": "Health Decile", "dtype": "numeric"})
    registry.append({"name": "imd_crime_decile", "category": "Deprivation", "label": "Crime Decile", "dtype": "numeric"})
    registry.append({"name": "imd_housing_decile", "category": "Deprivation", "label": "Housing Decile", "dtype": "numeric"})
    registry.append({"name": "imd_environment_decile", "category": "Deprivation", "label": "Environment Decile", "dtype": "numeric"})

    # Broadband
    registry.append({"name": "broadband_median_speed", "category": "Broadband", "label": "Median Download (Mbit/s)", "dtype": "numeric"})
    registry.append({"name": "broadband_superfast_pct", "category": "Broadband", "label": "Superfast Availability (%)", "dtype": "numeric"})
    registry.append({"name": "broadband_ultrafast_pct", "category": "Broadband", "label": "Ultrafast Availability (%)", "dtype": "numeric"})
    registry.append({"name": "broadband_full_fibre_pct", "category": "Broadband", "label": "Full Fibre Availability (%)", "dtype": "numeric"})

    # Schools
    registry.append({"name": "dist_nearest_primary_km", "category": "Schools", "label": "Dist. to Nearest Primary (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_secondary_km", "category": "Schools", "label": "Dist. to Nearest Secondary (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_primary_school", "category": "Schools", "label": "Nearest Primary School", "dtype": "categorical"})
    registry.append({"name": "nearest_secondary_school", "category": "Schools", "label": "Nearest Secondary School", "dtype": "categorical"})
    registry.append({"name": "nearest_primary_ofsted", "category": "Schools", "label": "Nearest Primary Ofsted", "dtype": "categorical"})
    registry.append({"name": "nearest_secondary_ofsted", "category": "Schools", "label": "Nearest Secondary Ofsted", "dtype": "categorical"})
    registry.append({"name": "dist_nearest_outstanding_primary_km", "category": "Schools", "label": "Dist. to Outstanding Primary (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_outstanding_secondary_km", "category": "Schools", "label": "Dist. to Outstanding Secondary (km)", "dtype": "numeric"})
    registry.append({"name": "primary_schools_within_2km", "category": "Schools", "label": "Primary Schools within 2km", "dtype": "numeric"})
    registry.append({"name": "secondary_schools_within_3km", "category": "Schools", "label": "Secondary Schools within 3km", "dtype": "numeric"})

    # Healthcare
    registry.append({"name": "dist_nearest_gp_km", "category": "Healthcare", "label": "Dist. to Nearest GP (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_gp_name", "category": "Healthcare", "label": "Nearest GP Practice", "dtype": "categorical"})
    registry.append({"name": "dist_nearest_hospital_km", "category": "Healthcare", "label": "Dist. to Nearest Hospital (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_hospital_name", "category": "Healthcare", "label": "Nearest Hospital", "dtype": "categorical"})
    registry.append({"name": "gp_practices_within_2km", "category": "Healthcare", "label": "GP Practices within 2km", "dtype": "numeric"})

    # Amenities (Supermarkets)
    registry.append({"name": "dist_nearest_supermarket_km", "category": "Amenities", "label": "Dist. to Nearest Supermarket (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_supermarket_name", "category": "Amenities", "label": "Nearest Supermarket", "dtype": "categorical"})
    registry.append({"name": "nearest_supermarket_brand", "category": "Amenities", "label": "Nearest Supermarket Brand", "dtype": "categorical"})
    registry.append({"name": "dist_nearest_premium_supermarket_km", "category": "Amenities", "label": "Dist. to Premium Supermarket (km)", "dtype": "numeric"})
    registry.append({"name": "dist_nearest_budget_supermarket_km", "category": "Amenities", "label": "Dist. to Budget Supermarket (km)", "dtype": "numeric"})
    registry.append({"name": "supermarkets_within_2km", "category": "Amenities", "label": "Supermarkets within 2km", "dtype": "numeric"})

    # Pubs
    registry.append({"name": "dist_nearest_pub_km", "category": "Pubs", "label": "Dist. to Nearest Pub (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_pub_name", "category": "Pubs", "label": "Nearest Pub", "dtype": "categorical"})
    registry.append({"name": "pubs_within_1km", "category": "Pubs", "label": "Pubs within 1km", "dtype": "numeric"})

    # Gyms
    registry.append({"name": "dist_nearest_gym_km", "category": "Gyms", "label": "Dist. to Nearest Gym (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_gym_name", "category": "Gyms", "label": "Nearest Gym", "dtype": "categorical"})
    registry.append({"name": "gyms_within_2km", "category": "Gyms", "label": "Gyms within 2km", "dtype": "numeric"})

    # Green Spaces
    registry.append({"name": "dist_nearest_park_km", "category": "Green Spaces", "label": "Dist. to Nearest Park (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_park_name", "category": "Green Spaces", "label": "Nearest Park", "dtype": "categorical"})
    registry.append({"name": "dist_nearest_green_space_km", "category": "Green Spaces", "label": "Dist. to Nearest Green Space (km)", "dtype": "numeric"})
    registry.append({"name": "nearest_green_space_name", "category": "Green Spaces", "label": "Nearest Green Space", "dtype": "categorical"})
    registry.append({"name": "green_spaces_within_1km", "category": "Green Spaces", "label": "Green Spaces within 1km", "dtype": "numeric"})

    # Crime
    registry.append({"name": "total_crime", "category": "Crime", "label": "Total Crime Count", "dtype": "numeric"})
    for cat, col in CRIME_COL_MAP.items():
        label = cat.replace("-", " ").title()
        registry.append({"name": col, "category": "Crime", "label": label, "dtype": "numeric"})

    # Parsed features
    for key in FEATURE_PARSER_KEYS:
        # Skip features already added above
        if key in ("epc_rating",):
            continue
        if key in _CATEGORICAL_FEATURES:
            dtype = "categorical"
        elif key in _NUMERIC_PARSED:
            dtype = "numeric"
        else:
            dtype = "boolean"
        label = key.replace("_", " ").title()
        registry.append({"name": key, "category": "Parsed Features", "label": label, "dtype": dtype})

    # Sale context
    registry.append({"name": "sale_year", "category": "Sale Context", "label": "Sale Year", "dtype": "numeric"})
    registry.append({"name": "sale_month", "category": "Sale Context", "label": "Sale Month", "dtype": "numeric"})
    registry.append({"name": "sale_quarter", "category": "Sale Context", "label": "Sale Quarter", "dtype": "numeric"})
    registry.append({"name": "tenure", "category": "Sale Context", "label": "Tenure", "dtype": "categorical"})

    return registry


FEATURE_REGISTRY = _build_registry()

TARGETS = [
    {"name": "price_numeric", "label": "Sale Price (£)"},
    {"name": "price_per_sqft", "label": "Price per Sq Ft (£)"},
    {"name": "price_change_pct", "label": "Price Change (%)"},
]


# ---------------------------------------------------------------------------
# Crime data aggregation
# ---------------------------------------------------------------------------

def _get_crime_by_postcode(db: Session) -> dict:
    """Load monthly crime data per postcode from CrimeStats table.

    Returns nested dict: {postcode: {YYYY-MM: {total: N, burglary: N, ...}}}
    Used for time-matched crime features — each sale gets trailing 12-month
    crime counts from the date of sale, not from today.
    """
    rows = (
        db.query(
            CrimeStats.postcode,
            CrimeStats.month,
            CrimeStats.category,
            CrimeStats.count,
        )
        .all()
    )

    # Build nested: {postcode: {month: {category: count}}}
    crime: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for postcode, month, category, count in rows:
        crime[postcode][month][category] += float(count or 0)
        crime[postcode][month]["_total"] += float(count or 0)

    return dict(crime)


def _aggregate_crime_window(
    crime_monthly: dict,
    sale_month: Optional[str],
    window: int = 12,
) -> dict:
    """Sum crime counts over trailing `window` months from sale_month.

    Args:
        crime_monthly: {YYYY-MM: {category: count, _total: N}}
        sale_month: YYYY-MM string (from sale.date_sold_iso[:7])
        window: number of months to look back (default 12)

    Returns dict with total_crime and per-category counts.
    """
    result = {"total_crime": None}
    for col in CRIME_COL_MAP.values():
        result[col] = None

    if not crime_monthly or not sale_month:
        return result

    # Generate the window of months to sum
    try:
        year, month = int(sale_month[:4]), int(sale_month[5:7])
    except (ValueError, IndexError):
        logger.debug("Invalid sale_month '%s', skipping crime window aggregation", sale_month)
        return result

    months_to_check = []
    for i in range(window):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        months_to_check.append(f"{y:04d}-{m:02d}")

    # Sum across the window
    total = 0.0
    cat_totals = defaultdict(float)
    found_any = False

    for m in months_to_check:
        month_data = crime_monthly.get(m)
        if month_data:
            found_any = True
            total += month_data.get("_total", 0)
            for cat, col in CRIME_COL_MAP.items():
                cat_totals[col] += month_data.get(cat, 0)

    if not found_any:
        return result

    result["total_crime"] = total
    for col in CRIME_COL_MAP.values():
        result[col] = cat_totals.get(col, 0.0)

    return result


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------

def assemble_dataset(
    db: Session,
    target: str,
    selected_features: list[str],
    on_progress: ProgressCallback | None = None,
) -> pd.DataFrame:
    """Build a modelling-ready DataFrame from the database.

    For price_numeric/price_per_sqft: uses latest sale per property.
    For price_change_pct: uses properties with 2+ sales.
    Returns DataFrame with feature columns + target + metadata columns
    (property_id, address, date_sold_iso).
    """
    if target == "price_change_pct":
        return _assemble_price_change(db, selected_features, on_progress)
    return _assemble_price(db, target, selected_features, on_progress)


def _assemble_price(
    db: Session,
    target: str,
    selected_features: list[str],
    on_progress: ProgressCallback | None = None,
) -> pd.DataFrame:
    """Assemble dataset for price or price_per_sqft targets.

    Uses ALL sales per property (not just the latest), giving more training
    rows and letting the model learn temporal price trends via sale_year/month.

    Queries the DB in batches of _ASSEMBLY_BATCH_SIZE to avoid OOM on large
    datasets.  Each batch is converted to a DataFrame independently so that
    the intermediate list-of-dicts can be freed before the next batch.
    """
    total_rows = (
        db.query(func.count(Sale.id))
        .filter(Sale.price_numeric.isnot(None))
        .scalar()
    ) or 0

    if not total_rows:
        return pd.DataFrame()

    if on_progress:
        on_progress(0.01, f"Assembling dataset ({total_rows:,} sales)")

    # Pre-compute which columns are actually needed so we only SELECT
    # and process the columns the user selected.
    needed = frozenset(selected_features)
    if target == "price_per_sqft":
        needed = needed | {"sq_ft"}

    # Build Core query columns — no ORM object construction, just
    # lightweight Row tuples with only the columns we need.
    columns, need_parsed, need_crime = _assembly_columns(needed)
    crime_data = _get_crime_by_postcode(db) if need_crime else {}
    crime_cache: dict[tuple, dict] = {}
    n_batches = (total_rows + _ASSEMBLY_BATCH_SIZE - 1) // _ASSEMBLY_BATCH_SIZE
    dfs: list[pd.DataFrame] = []

    # Keyset pagination: WHERE Sale.id > last_seen_id is O(n) total,
    # vs OFFSET which is O(n²) because the DB must skip rows each time.
    last_id = 0

    for i in range(n_batches):
        stmt = (
            select(*columns)
            .select_from(_PROP_T.join(_SALE_T, _PROP_T.c.id == _SALE_T.c.property_id))
            .where(_SALE_T.c.price_numeric.isnot(None), _SALE_T.c.id > last_id)
            .order_by(_SALE_T.c.id)
            .limit(_ASSEMBLY_BATCH_SIZE)
        )
        rows = db.execute(stmt).fetchall()
        if not rows:
            break

        last_id = rows[-1].sale_id

        if on_progress:
            pct = 0.01 + 0.04 * ((i + 1) / n_batches)
            on_progress(pct, f"Assembling batch {i + 1}/{n_batches} ({len(rows):,} rows)")

        records = [
            _record_from_row(row, needed, crime_data, crime_cache, need_parsed, need_crime)
            for row in rows
        ]
        batch_df = pd.DataFrame(records)
        del records
        dfs.append(batch_df)

    logger.info("Assembled %d batches, concatenating", len(dfs))
    df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
    del dfs

    # Computed target: price_per_sqft (vectorized — avoids slow row-by-row apply)
    if target == "price_per_sqft":
        valid = (df["sq_ft"] > 0) & df["sq_ft"].notna() & df["price_numeric"].notna()
        df.loc[valid, "price_per_sqft"] = df.loc[valid, "price_numeric"] / df.loc[valid, "sq_ft"]
        df = df.dropna(subset=["price_per_sqft"])

    # Filter to rows with valid target
    df = df.dropna(subset=[target])

    # Convert dtypes
    _convert_dtypes(df, selected_features)

    return df


def _assemble_price_change(
    db: Session,
    selected_features: list[str],
    on_progress: ProgressCallback | None = None,
) -> pd.DataFrame:
    """Assemble dataset for price_change_pct target.

    Properties must have 2+ sales. Computes % change between
    second-most-recent and most-recent sale.

    Queries properties in batches of _ASSEMBLY_BATCH_SIZE to avoid OOM.
    """
    # Get property IDs with 2+ sales (just IDs — small result set)
    prop_ids = [
        row[0]
        for row in db.query(Sale.property_id)
        .group_by(Sale.property_id)
        .having(func.count(Sale.id) >= 2)
        .all()
    ]

    if not prop_ids:
        return pd.DataFrame()

    if on_progress:
        on_progress(0.01, f"Assembling price-change dataset ({len(prop_ids):,} properties)")

    needed = frozenset(selected_features)
    need_crime = bool(needed & _CRIME_FEATURES)
    crime_data = _get_crime_by_postcode(db) if need_crime else {}
    crime_cache: dict[tuple, dict] = {}
    n_batches = (len(prop_ids) + _ASSEMBLY_BATCH_SIZE - 1) // _ASSEMBLY_BATCH_SIZE
    dfs: list[pd.DataFrame] = []

    for i in range(n_batches):
        batch_ids = prop_ids[i * _ASSEMBLY_BATCH_SIZE : (i + 1) * _ASSEMBLY_BATCH_SIZE]

        if on_progress:
            pct = 0.01 + 0.04 * ((i + 1) / n_batches)
            on_progress(pct, f"Assembling batch {i + 1}/{n_batches} ({len(batch_ids):,} properties)")

        properties = (
            db.query(Property)
            .filter(Property.id.in_(batch_ids))
            .all()
        )

        records = []
        for prop in properties:
            sales = sorted(
                [s for s in prop.sales if s.price_numeric],
                key=lambda s: s.date_sold_iso or "",
            )
            if len(sales) < 2:
                continue

            prev_sale = sales[-2]
            latest_sale = sales[-1]

            if not prev_sale.price_numeric or prev_sale.price_numeric == 0:
                continue

            pct_change = (
                (latest_sale.price_numeric - prev_sale.price_numeric)
                / prev_sale.price_numeric * 100
            )

            record = _build_record(prop, latest_sale, crime_data, crime_cache, needed)
            record["price_change_pct"] = round(pct_change, 2)
            records.append(record)

        if records:
            dfs.append(pd.DataFrame(records))
            del records

        db.expire_all()

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
    del dfs

    df = df.dropna(subset=["price_change_pct"])
    _convert_dtypes(df, selected_features)
    return df


def _to_float(val) -> float:
    """Coerce a value to float, returning NaN for None/non-numeric.

    By ensuring every numeric cell is a Python float (or NaN) *before*
    DataFrame construction, pandas will infer float64 dtype directly
    instead of falling back to object dtype.  This avoids the expensive
    post-hoc pd.to_numeric conversion that was causing a 2.6 GiB
    temporary allocation on large datasets.
    """
    if val is None:
        return np.nan
    try:
        f = float(val)
        return f if math.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


# Map of feature name → (attribute_source, attribute_name, is_numeric)
# attribute_source: "prop" or "sale"
# Used by _build_record to selectively load only needed columns.
_PROP_NUMERIC_ATTRS: dict[str, str] = {
    "bedrooms": "bedrooms", "bathrooms": "bathrooms",
    "epc_score": "epc_score", "epc_environment_impact": "epc_environment_impact",
    "estimated_energy_cost": "estimated_energy_cost",
    "latitude": "latitude", "longitude": "longitude",
    "dist_nearest_rail_km": "dist_nearest_rail_km",
    "dist_nearest_tube_km": "dist_nearest_tube_km",
    "dist_nearest_bus_km": "dist_nearest_bus_km",
    "dist_nearest_airport_km": "dist_nearest_airport_km",
    "dist_nearest_port_km": "dist_nearest_port_km",
    "bus_stops_within_500m": "bus_stops_within_500m",
    "imd_decile": "imd_decile", "imd_income_decile": "imd_income_decile",
    "imd_employment_decile": "imd_employment_decile",
    "imd_education_decile": "imd_education_decile",
    "imd_health_decile": "imd_health_decile",
    "imd_crime_decile": "imd_crime_decile",
    "imd_housing_decile": "imd_housing_decile",
    "imd_environment_decile": "imd_environment_decile",
    "broadband_median_speed": "broadband_median_speed",
    "broadband_superfast_pct": "broadband_superfast_pct",
    "broadband_ultrafast_pct": "broadband_ultrafast_pct",
    "broadband_full_fibre_pct": "broadband_full_fibre_pct",
    "dist_nearest_primary_km": "dist_nearest_primary_km",
    "dist_nearest_secondary_km": "dist_nearest_secondary_km",
    "dist_nearest_outstanding_primary_km": "dist_nearest_outstanding_primary_km",
    "dist_nearest_outstanding_secondary_km": "dist_nearest_outstanding_secondary_km",
    "primary_schools_within_2km": "primary_schools_within_2km",
    "secondary_schools_within_3km": "secondary_schools_within_3km",
    "dist_nearest_gp_km": "dist_nearest_gp_km",
    "dist_nearest_hospital_km": "dist_nearest_hospital_km",
    "gp_practices_within_2km": "gp_practices_within_2km",
    "dist_nearest_supermarket_km": "dist_nearest_supermarket_km",
    "dist_nearest_premium_supermarket_km": "dist_nearest_premium_supermarket_km",
    "dist_nearest_budget_supermarket_km": "dist_nearest_budget_supermarket_km",
    "supermarkets_within_2km": "supermarkets_within_2km",
    "dist_nearest_pub_km": "dist_nearest_pub_km",
    "pubs_within_1km": "pubs_within_1km",
    "dist_nearest_gym_km": "dist_nearest_gym_km",
    "gyms_within_2km": "gyms_within_2km",
    "dist_nearest_park_km": "dist_nearest_park_km",
    "dist_nearest_green_space_km": "dist_nearest_green_space_km",
    "green_spaces_within_1km": "green_spaces_within_1km",
}

_PROP_STRING_ATTRS: dict[str, str] = {
    "property_type": "property_type", "flood_risk_level": "flood_risk_level",
    "nearest_rail_station": "nearest_rail_station",
    "nearest_tube_station": "nearest_tube_station",
    "nearest_airport": "nearest_airport", "nearest_port": "nearest_port",
    "nearest_primary_school": "nearest_primary_school",
    "nearest_secondary_school": "nearest_secondary_school",
    "nearest_primary_ofsted": "nearest_primary_ofsted",
    "nearest_secondary_ofsted": "nearest_secondary_ofsted",
    "nearest_gp_name": "nearest_gp_name",
    "nearest_hospital_name": "nearest_hospital_name",
    "nearest_supermarket_name": "nearest_supermarket_name",
    "nearest_supermarket_brand": "nearest_supermarket_brand",
    "nearest_pub_name": "nearest_pub_name",
    "nearest_gym_name": "nearest_gym_name",
    "nearest_park_name": "nearest_park_name",
    "nearest_green_space_name": "nearest_green_space_name",
}

# All crime-related feature names
_CRIME_FEATURES = {"total_crime"} | set(CRIME_COL_MAP.values())

# All parsed feature names (from FEATURE_PARSER_KEYS)
_PARSED_FEATURES = set(FEATURE_PARSER_KEYS)

# Table references for Core queries (no ORM overhead)
_PROP_T = Property.__table__
_SALE_T = Sale.__table__


def _assembly_columns(needed: frozenset[str]) -> tuple[list, bool, bool]:
    """Build the SELECT column list for a Core query.

    Returns (columns, need_parsed, need_crime) so the caller knows
    which processing blocks to run in _record_from_row.
    Only selects columns that are in `needed`, plus always-required
    metadata/target columns.
    """
    cols = [
        _PROP_T.c.id.label("property_id"),
        _PROP_T.c.address,
        _SALE_T.c.id.label("sale_id"),
        _SALE_T.c.date_sold_iso,
        _SALE_T.c.price_numeric,
    ]

    if "tenure" in needed:
        cols.append(_SALE_T.c.tenure)

    for col_name in _PROP_NUMERIC_ATTRS:
        if col_name in needed:
            cols.append(_PROP_T.c[col_name])

    for col_name in _PROP_STRING_ATTRS:
        if col_name in needed:
            cols.append(_PROP_T.c[col_name])

    need_parsed = bool(needed & _PARSED_FEATURES)
    if need_parsed:
        cols.append(_PROP_T.c.extra_features)

    need_crime = bool(needed & _CRIME_FEATURES)
    if need_crime:
        cols.append(_PROP_T.c.postcode)

    return cols, need_parsed, need_crime


def _record_from_row(
    row,
    needed: frozenset[str],
    crime_data: dict,
    crime_cache: dict[tuple, dict],
    need_parsed: bool,
    need_crime: bool,
) -> dict:
    """Build a record dict from a Core query Row (no ORM objects).

    Much faster than _build_record because Row tuples skip ORM
    hydration overhead (identity map, descriptors, relationship
    machinery) for 70+ columns × 50k rows per batch.
    """
    _f = _to_float

    record: dict = {
        "property_id": row.property_id,
        "address": row.address,
        "date_sold_iso": row.date_sold_iso,
        "price_numeric": _f(row.price_numeric),
    }

    # Sale date features
    if row.date_sold_iso:
        try:
            parts = row.date_sold_iso.split("-")
            year, month = int(parts[0]), int(parts[1])
            if "sale_year" in needed:
                record["sale_year"] = float(year)
            if "sale_month" in needed:
                record["sale_month"] = float(month)
            if "sale_quarter" in needed:
                record["sale_quarter"] = float((month - 1) // 3 + 1)
        except (IndexError, ValueError):
            pass

    if "tenure" in needed:
        record["tenure"] = row.tenure

    # Property columns — only those selected and already in the Row
    for col_name in _PROP_NUMERIC_ATTRS:
        if col_name in needed:
            record[col_name] = _f(getattr(row, col_name))

    for col_name in _PROP_STRING_ATTRS:
        if col_name in needed:
            record[col_name] = getattr(row, col_name)

    # Parsed extra features
    if need_parsed:
        parsed = parse_all_features(row.extra_features)
        for key in FEATURE_PARSER_KEYS:
            if key not in needed:
                continue
            val = parsed.get(key)
            if key in _CATEGORICAL_FEATURES:
                record[key] = val
            elif key in _BOOLEAN_PARSED:
                record[key] = 1.0 if val is True else (0.0 if val is False else np.nan)
            elif key in _NUMERIC_PARSED:
                record[key] = _f(val)
            else:
                record[key] = val

    # Crime data
    if need_crime:
        sale_month_str = (
            row.date_sold_iso[:7]
            if row.date_sold_iso and len(row.date_sold_iso) >= 7
            else None
        )
        cache_key = (row.postcode, sale_month_str)

        if cache_key in crime_cache:
            crime_window = crime_cache[cache_key]
        else:
            postcode_crime_monthly = crime_data.get(row.postcode, {})
            crime_window = _aggregate_crime_window(postcode_crime_monthly, sale_month_str)
            crime_cache[cache_key] = crime_window

        if "total_crime" in needed:
            record["total_crime"] = _f(crime_window.get("total_crime"))
        for col in CRIME_COL_MAP.values():
            if col in needed:
                record[col] = _f(crime_window.get(col))

    return record


def _build_record(
    prop: Property, sale: Sale, crime_data: dict[str, dict[str, float]],
    crime_cache: dict[tuple, dict] | None = None,
    needed: frozenset[str] | None = None,
) -> dict:
    """Build a single row dict from Property + Sale + crime data.

    If `needed` is provided, only populate columns in that set (plus
    metadata and target columns which are always included).  This skips
    expensive work like JSON parsing and crime aggregation when those
    feature groups aren't selected.
    """
    _f = _to_float

    # Metadata + target — always included
    record: dict = {
        "property_id": prop.id,
        "address": prop.address,
        "date_sold_iso": sale.date_sold_iso,
        "price_numeric": _f(sale.price_numeric),
    }

    # Sale date features
    sale_year = None
    sale_month = None
    sale_quarter = None
    if sale.date_sold_iso:
        try:
            parts = sale.date_sold_iso.split("-")
            sale_year = int(parts[0])
            sale_month = int(parts[1])
            sale_quarter = (sale_month - 1) // 3 + 1
        except (IndexError, ValueError):
            pass

    if needed is None or "sale_year" in needed:
        record["sale_year"] = _f(sale_year)
    if needed is None or "sale_month" in needed:
        record["sale_month"] = _f(sale_month)
    if needed is None or "sale_quarter" in needed:
        record["sale_quarter"] = _f(sale_quarter)
    if needed is None or "tenure" in needed:
        record["tenure"] = sale.tenure

    # Property numeric columns — only those in `needed`
    for col, attr in _PROP_NUMERIC_ATTRS.items():
        if needed is None or col in needed:
            record[col] = _f(getattr(prop, attr))

    # Property string columns — only those in `needed`
    for col, attr in _PROP_STRING_ATTRS.items():
        if needed is None or col in needed:
            record[col] = getattr(prop, attr)

    # Parsed extra features — skip entirely if none are selected
    if needed is None or needed & _PARSED_FEATURES:
        parsed = parse_all_features(prop.extra_features)
        for key in FEATURE_PARSER_KEYS:
            if needed is not None and key not in needed:
                continue
            val = parsed.get(key)
            if key in _CATEGORICAL_FEATURES:
                record[key] = val
            elif key in _BOOLEAN_PARSED:
                record[key] = 1.0 if val is True else (0.0 if val is False else np.nan)
            elif key in _NUMERIC_PARSED:
                record[key] = _f(val)
            else:
                record[key] = val

    # Crime data — skip entirely if no crime features selected
    if needed is None or needed & _CRIME_FEATURES:
        sale_month_str = sale.date_sold_iso[:7] if sale.date_sold_iso and len(sale.date_sold_iso) >= 7 else None
        cache_key = (prop.postcode, sale_month_str)

        if crime_cache is not None and cache_key in crime_cache:
            crime_window = crime_cache[cache_key]
        else:
            postcode_crime_monthly = crime_data.get(prop.postcode, {})
            crime_window = _aggregate_crime_window(postcode_crime_monthly, sale_month_str)
            if crime_cache is not None:
                crime_cache[cache_key] = crime_window

        if needed is None or "total_crime" in needed:
            record["total_crime"] = _f(crime_window.get("total_crime"))
        for col in CRIME_COL_MAP.values():
            if needed is None or col in needed:
                record[col] = _f(crime_window.get(col))

    return record


# Columns that must stay float64 for precision (prices, coordinates)
_FLOAT64_COLUMNS = {
    "price_numeric", "price_per_sqft", "price_change_pct",
    "latitude", "longitude",
    "estimated_energy_cost", "service_charge", "ground_rent",
}

# Small-integer columns (guaranteed -128..127) → nullable Int8 (1 byte vs 8)
# Only truly bounded values: deciles (1-10), bedrooms/bathrooms (0-~20),
# booleans (0/1), month (1-12), quarter (1-4), receptions (0-~10).
_INT8_COLUMNS = (
    {
        "bedrooms", "bathrooms",
        "imd_decile", "imd_income_decile", "imd_employment_decile",
        "imd_education_decile", "imd_health_decile", "imd_crime_decile",
        "imd_housing_decile", "imd_environment_decile",
        "receptions", "sale_month", "sale_quarter",
    }
    | _BOOLEAN_PARSED
)

# Medium-integer columns (can exceed 127) → nullable Int16 (2 bytes)
_INT16_COLUMNS = {
    "sale_year", "lease_years",
    "epc_score", "epc_environment_impact",
    "bus_stops_within_500m",
    "primary_schools_within_2km", "secondary_schools_within_3km",
    "gp_practices_within_2km", "supermarkets_within_2km",
    "green_spaces_within_1km", "pubs_within_1km", "gyms_within_2km",
}


def _downcast_numeric(df: pd.DataFrame) -> None:
    """Downcast numeric columns to the smallest safe dtype.

    At 5.5M rows this cuts memory dramatically:
      - ~80 boolean + ~20 small-int cols: float64 (8B) → Int8 (1B) = 87% saving
      - 2 medium-int cols: float64 (8B) → Int16 (2B) = 75% saving
      - ~10 distance/pct cols: float64 (8B) → float32 (4B) = 50% saving
      - ~7 price/coord cols: kept at float64 for precision

    Uses clip + round before casting to prevent "cannot safely cast"
    errors from float imprecision or out-of-range values.
    """
    for col in df.select_dtypes(include=["float64"]).columns:
        if col in _FLOAT64_COLUMNS:
            continue
        if col in _INT8_COLUMNS:
            df[col] = df[col].clip(-128, 127).round().astype(pd.Int8Dtype())
        elif col in _INT16_COLUMNS:
            df[col] = df[col].clip(-32768, 32767).round().astype(pd.Int16Dtype())
        else:
            df[col] = df[col].astype(np.float32)


def _convert_dtypes(df: pd.DataFrame, selected_features: list[str]) -> None:
    """Convert column dtypes for ML: categoricals + downcast numerics.

    Numeric and boolean columns are already float64 from _build_record().
    We cast categoricals to pd.Categorical and downcast non-critical
    float64 columns to float32 to roughly halve memory usage.
    """
    _metadata = {"property_id", "address", "date_sold_iso"}
    for col in df.columns:
        if col in _metadata:
            continue
        if col in _CATEGORICAL_FEATURES:
            df[col] = df[col].astype("category")

    _downcast_numeric(df)


# ---------------------------------------------------------------------------
# Single property assembly (for prediction)
# ---------------------------------------------------------------------------

def assemble_single_property(
    db: Session,
    property_id: int,
    feature_names: list[str],
    categorical_features: list[str],
    prediction_date: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Assemble a single-row DataFrame for prediction.

    If prediction_date is provided (YYYY-MM-DD), overrides sale_year/month/quarter.
    """
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        return None

    # Get latest sale for tenure info
    latest_sale = (
        db.query(Sale)
        .filter(Sale.property_id == property_id)
        .order_by(Sale.date_sold_iso.desc())
        .first()
    )

    crime_data = _get_crime_by_postcode(db)
    sale_stub = latest_sale or Sale(tenure="", price_numeric=0, date_sold_iso="")
    record = _build_record(prop, sale_stub, crime_data)

    # Override date features if prediction_date provided
    if prediction_date:
        try:
            parts = prediction_date.split("-")
            record["sale_year"] = float(parts[0])
            record["sale_month"] = float(parts[1])
            record["sale_quarter"] = float((int(parts[1]) - 1) // 3 + 1)
        except (IndexError, ValueError):
            pass

    df = pd.DataFrame([record])

    # Keep only the feature columns
    available = [f for f in feature_names if f in df.columns]
    df = df[available]

    # Match training dtypes — categoricals become pd.Categorical,
    # everything else is already float64 from _build_record()
    for col in df.columns:
        if col in categorical_features:
            df[col] = df[col].astype("category")

    return df
