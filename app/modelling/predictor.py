"""Single-property and postcode-level prediction using a trained model."""

import logging
from typing import Optional

import xgboost as xgb
from sqlalchemy.orm import Session

from ..models import Property, Sale
from .data_assembly import assemble_single_property
from .trainer import _model_store

logger = logging.getLogger(__name__)


def predict_single(
    model_id: str,
    db: Session,
    property_id: int,
    prediction_date: Optional[str] = None,
) -> Optional[dict]:
    """Predict using a stored model for a single property.

    Returns None if model_id not found.
    Raises ValueError if property not found.
    """
    entry = _model_store.get(model_id)
    if not entry:
        return None

    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise ValueError(f"Property {property_id} not found")

    model = entry["model"]
    feature_names = entry["features"]
    model_type = entry["model_type"]
    cat_features = entry["categorical_features"]

    df = assemble_single_property(
        db, property_id, feature_names, cat_features, prediction_date,
    )
    if df is None or df.empty:
        raise ValueError(f"Could not assemble features for property {property_id}")

    # Predict
    if model_type == "xgboost":
        dmat = xgb.DMatrix(df, enable_categorical=True)
        pred = model.predict(dmat)
    else:
        pred = model.predict(df)

    return {
        "property_id": property_id,
        "address": prop.address,
        "predicted_value": round(float(pred[0]), 2),
    }


def predict_postcode(
    model_id: str,
    db: Session,
    postcode: str,
    limit: int = 50,
    prediction_date: Optional[str] = None,
) -> Optional[list]:
    """Predict for all properties in a postcode.

    Returns None if model_id not found.
    Returns list of prediction dicts sorted by predicted_value desc.
    """
    entry = _model_store.get(model_id)
    if not entry:
        return None

    model = entry["model"]
    feature_names = entry["features"]
    model_type = entry["model_type"]
    cat_features = entry["categorical_features"]
    # Find properties in this postcode
    props = (
        db.query(Property)
        .filter(Property.postcode == postcode.upper().strip())
        .limit(limit)
        .all()
    )

    if not props:
        raise ValueError(f"No properties found for postcode '{postcode}'")

    # Get latest sale price for each property (for comparison)
    latest_sales = {}
    for prop in props:
        sale = (
            db.query(Sale)
            .filter(Sale.property_id == prop.id, Sale.price_numeric.isnot(None))
            .order_by(Sale.id.desc())
            .first()
        )
        if sale:
            latest_sales[prop.id] = sale.price_numeric

    results = []
    for prop in props:
        try:
            df = assemble_single_property(
                db, prop.id, feature_names, cat_features, prediction_date,
            )
            if df is None or df.empty:
                continue

            if model_type == "xgboost":
                dmat = xgb.DMatrix(df, enable_categorical=True)
                pred = model.predict(dmat)
            else:
                pred = model.predict(df)

            predicted = round(float(pred[0]), 2)
            last_sale = latest_sales.get(prop.id)

            results.append({
                "property_id": prop.id,
                "address": prop.address,
                "predicted_value": predicted,
                "last_sale_price": last_sale,
                "difference": round(predicted - last_sale, 2) if last_sale else None,
                "difference_pct": round((predicted - last_sale) / last_sale * 100, 1) if last_sale else None,
            })
        except Exception:
            logger.debug("Skipping property %d: prediction failed", prop.id)
            continue

    # Sort by predicted value descending
    results.sort(key=lambda r: r["predicted_value"], reverse=True)
    return results
