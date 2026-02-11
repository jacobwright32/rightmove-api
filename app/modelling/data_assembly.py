"""Data assembly for ML modelling.

Joins Property + Sale + CrimeStats, parses extra_features, and builds
a pandas DataFrame ready for model training or single-row prediction.
"""

import logging
from collections import defaultdict
from typing import Optional

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..feature_parser import _ALL_KEYS, parse_all_features
from ..models import CrimeStats, Property, Sale

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature registry — served to the frontend for the feature selection UI
# ---------------------------------------------------------------------------

# Categorical string features (need pd.Categorical dtype)
_CATEGORICAL_FEATURES = {
    "property_type", "epc_rating", "parking", "garden", "heating",
    "lease_type", "furnished", "floor_level", "council_tax_band",
    "flood_risk_level", "tenure",
    "nearest_rail_station", "nearest_tube_station", "nearest_airport", "nearest_port",
}

# Numeric features from parsed extras
_NUMERIC_PARSED = {
    "lease_years", "receptions", "sq_ft", "service_charge",
    "ground_rent", "distance_to_station",
}

# Boolean features from parsed extras (everything in _ALL_KEYS that isn't
# categorical or numeric)
_BOOLEAN_PARSED = set(_ALL_KEYS) - _CATEGORICAL_FEATURES - _NUMERIC_PARSED

# Top crime categories to include as separate features
CRIME_CATEGORIES = [
    "anti-social-behaviour",
    "burglary",
    "violence-and-sexual-offences",
    "criminal-damage-and-arson",
    "drugs",
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

    # Crime
    registry.append({"name": "total_crime", "category": "Crime", "label": "Total Crime Count", "dtype": "numeric"})
    for cat, col in CRIME_COL_MAP.items():
        label = cat.replace("-", " ").title()
        registry.append({"name": col, "category": "Crime", "label": label, "dtype": "numeric"})

    # Parsed features
    for key in _ALL_KEYS:
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
) -> pd.DataFrame:
    """Build a modelling-ready DataFrame from the database.

    For price_numeric/price_per_sqft: uses latest sale per property.
    For price_change_pct: uses properties with 2+ sales.
    Returns DataFrame with feature columns + target + metadata columns
    (property_id, address, date_sold_iso).
    """
    if target == "price_change_pct":
        return _assemble_price_change(db, selected_features)
    return _assemble_price(db, target, selected_features)


def _assemble_price(
    db: Session,
    target: str,
    selected_features: list[str],
) -> pd.DataFrame:
    """Assemble dataset for price or price_per_sqft targets."""
    # Get latest sale per property via subquery
    latest_sale = (
        db.query(Sale.property_id, func.max(Sale.id).label("max_id"))
        .group_by(Sale.property_id)
        .subquery()
    )
    rows = (
        db.query(Property, Sale)
        .join(latest_sale, Property.id == latest_sale.c.property_id)
        .join(Sale, Sale.id == latest_sale.c.max_id)
        .filter(Sale.price_numeric.isnot(None))
        .all()
    )

    if not rows:
        return pd.DataFrame()

    crime_data = _get_crime_by_postcode(db)
    records = []
    for prop, sale in rows:
        record = _build_record(prop, sale, crime_data)
        records.append(record)

    df = pd.DataFrame(records)

    # Computed target: price_per_sqft
    if target == "price_per_sqft":
        df["price_per_sqft"] = df.apply(
            lambda r: r["price_numeric"] / r["sq_ft"]
            if r.get("sq_ft") and r["sq_ft"] > 0 and r.get("price_numeric")
            else None,
            axis=1,
        )
        df = df.dropna(subset=["price_per_sqft"])

    # Filter to rows with valid target
    df = df.dropna(subset=[target])

    # Convert dtypes
    _convert_dtypes(df, selected_features)

    return df


def _assemble_price_change(
    db: Session,
    selected_features: list[str],
) -> pd.DataFrame:
    """Assemble dataset for price_change_pct target.

    Properties must have 2+ sales. Computes % change between
    second-most-recent and most-recent sale.
    """
    # Get properties with 2+ sales
    props_with_sales = (
        db.query(Sale.property_id)
        .group_by(Sale.property_id)
        .having(func.count(Sale.id) >= 2)
        .subquery()
    )
    properties = (
        db.query(Property)
        .filter(Property.id.in_(db.query(props_with_sales.c.property_id)))
        .all()
    )

    if not properties:
        return pd.DataFrame()

    crime_data = _get_crime_by_postcode(db)
    records = []
    for prop in properties:
        # Get sales ordered by date
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

        record = _build_record(prop, latest_sale, crime_data)
        record["price_change_pct"] = round(pct_change, 2)
        records.append(record)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    df = df.dropna(subset=["price_change_pct"])
    _convert_dtypes(df, selected_features)
    return df


def _build_record(
    prop: Property, sale: Sale, crime_data: dict[str, dict[str, float]],
) -> dict:
    """Build a single row dict from Property + Sale + crime data."""
    # Parse sale date into year/month/quarter
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

    # Base property fields
    record: dict = {
        "property_id": prop.id,
        "address": prop.address,
        "date_sold_iso": sale.date_sold_iso,
        "price_numeric": sale.price_numeric,
        "bedrooms": prop.bedrooms,
        "bathrooms": prop.bathrooms,
        "property_type": prop.property_type,
        "epc_score": prop.epc_score,
        "epc_environment_impact": prop.epc_environment_impact,
        "estimated_energy_cost": prop.estimated_energy_cost,
        "flood_risk_level": prop.flood_risk_level,
        "latitude": prop.latitude,
        "longitude": prop.longitude,
        # Transport distances
        "dist_nearest_rail_km": prop.dist_nearest_rail_km,
        "dist_nearest_tube_km": prop.dist_nearest_tube_km,
        "dist_nearest_bus_km": prop.dist_nearest_bus_km,
        "dist_nearest_airport_km": prop.dist_nearest_airport_km,
        "dist_nearest_port_km": prop.dist_nearest_port_km,
        "bus_stops_within_500m": prop.bus_stops_within_500m,
        "nearest_rail_station": prop.nearest_rail_station,
        "nearest_tube_station": prop.nearest_tube_station,
        "nearest_airport": prop.nearest_airport,
        "nearest_port": prop.nearest_port,
        "sale_year": sale_year,
        "sale_month": sale_month,
        "sale_quarter": sale_quarter,
        "tenure": sale.tenure,
    }

    # Parsed extra features
    parsed = parse_all_features(prop.extra_features)
    for key in _ALL_KEYS:
        record[key] = parsed.get(key)

    # Crime data — time-matched trailing 12-month window from sale date
    postcode_crime_monthly = crime_data.get(prop.postcode, {})
    sale_month_str = sale.date_sold_iso[:7] if sale.date_sold_iso and len(sale.date_sold_iso) >= 7 else None
    crime_window = _aggregate_crime_window(postcode_crime_monthly, sale_month_str)
    record["total_crime"] = crime_window.get("total_crime")
    for col in CRIME_COL_MAP.values():
        record[col] = crime_window.get(col)

    return record


def _convert_dtypes(df: pd.DataFrame, selected_features: list[str]) -> None:
    """Convert column dtypes for ML: categoricals + booleans + numerics."""
    _metadata = {"property_id", "address", "date_sold_iso"}
    for col in df.columns:
        if col in _metadata:
            continue
        if col in _CATEGORICAL_FEATURES:
            df[col] = df[col].astype("category")
        elif col in _BOOLEAN_PARSED:
            # Convert bool/None to float (True=1, False=0, None=NaN)
            df[col] = df[col].map(
                {True: 1.0, False: 0.0, None: float("nan")}
            ).astype(float)
        elif df[col].dtype == object:
            # Coerce any remaining object columns (e.g. crime data with Nones)
            df[col] = pd.to_numeric(df[col], errors="coerce")


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
        .order_by(Sale.id.desc())
        .first()
    )

    crime_data = _get_crime_by_postcode(db)
    sale_stub = latest_sale or Sale(tenure="", price_numeric=0, date_sold_iso="")
    record = _build_record(prop, sale_stub, crime_data)

    # Override date features if prediction_date provided
    if prediction_date:
        try:
            parts = prediction_date.split("-")
            record["sale_year"] = int(parts[0])
            record["sale_month"] = int(parts[1])
            record["sale_quarter"] = (int(parts[1]) - 1) // 3 + 1
        except (IndexError, ValueError):
            pass

    df = pd.DataFrame([record])

    # Keep only the feature columns
    available = [f for f in feature_names if f in df.columns]
    df = df[available]

    # Match training dtypes — force all non-categorical columns to float
    for col in df.columns:
        if col in categorical_features:
            df[col] = df[col].astype("category")
        elif col in _BOOLEAN_PARSED:
            df[col] = df[col].map(
                {True: 1.0, False: 0.0, None: float("nan")}
            ).astype(float)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

    return df
