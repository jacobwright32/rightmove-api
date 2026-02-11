"""Single-property prediction using a trained model."""

import logging
from typing import Optional

import xgboost as xgb
from sqlalchemy.orm import Session

from ..models import Property
from .data_assembly import assemble_single_property
from .trainer import _model_store

logger = logging.getLogger(__name__)


def predict_single(
    model_id: str,
    db: Session,
    property_id: int,
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

    df = assemble_single_property(db, property_id, feature_names, cat_features)
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
