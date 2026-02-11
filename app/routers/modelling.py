"""Modelling router — train models and predict property prices."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..modelling.data_assembly import FEATURE_REGISTRY, TARGETS, assemble_dataset
from ..modelling.predictor import predict_single
from ..modelling.trainer import train_model
from ..models import Sale
from ..schemas import (
    AvailableFeaturesResponse,
    FeatureInfo,
    SinglePredictionResponse,
    TargetInfo,
    TrainRequest,
    TrainResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model", tags=["modelling"])

_VALID_TARGETS = {t["name"] for t in TARGETS}
_VALID_MODEL_TYPES = {"lightgbm", "xgboost"}
_MIN_TRAINING_ROWS = 20


@router.get("/features", response_model=AvailableFeaturesResponse)
def get_features(db: Session = Depends(get_db)):
    """Return available features, targets, and dataset size."""
    # Count properties that have at least one sale with a price
    count = (
        db.query(func.count(func.distinct(Sale.property_id)))
        .filter(Sale.price_numeric.isnot(None))
        .scalar()
    ) or 0

    return AvailableFeaturesResponse(
        features=[FeatureInfo(**f) for f in FEATURE_REGISTRY],
        targets=[TargetInfo(**t) for t in TARGETS],
        total_properties_with_sales=count,
    )


@router.post("/train", response_model=TrainResponse)
def train(request: TrainRequest, db: Session = Depends(get_db)):
    """Train a model on the dataset."""
    # Validate target
    if request.target not in _VALID_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target '{request.target}'. Must be one of: {sorted(_VALID_TARGETS)}",
        )

    # Validate model type
    if request.model_type not in _VALID_MODEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{request.model_type}'. Must be one of: {sorted(_VALID_MODEL_TYPES)}",
        )

    # Validate features
    if not request.features:
        raise HTTPException(status_code=400, detail="At least one feature is required")

    # Assemble dataset
    try:
        df = assemble_dataset(db, request.target, request.features)
    except Exception as e:
        logger.exception("Dataset assembly failed")
        raise HTTPException(
            status_code=500, detail=f"Dataset assembly failed: {e}",
        ) from e

    if df.empty or len(df) < _MIN_TRAINING_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data: {len(df)} rows (minimum {_MIN_TRAINING_ROWS} required)",
        )

    # Train model
    try:
        result = train_model(
            df=df,
            target=request.target,
            feature_names=request.features,
            model_type=request.model_type,
            split_strategy=request.split_strategy,
            split_params=request.split_params,
            hyperparameters=request.hyperparameters,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Model training failed")
        raise HTTPException(
            status_code=500, detail=f"Training failed: {e}",
        ) from e

    return TrainResponse(**result)


@router.get("/{model_id}/predict", response_model=SinglePredictionResponse)
def predict(model_id: str, property_id: int, db: Session = Depends(get_db)):
    """Predict the target value for a single property using a trained model."""
    try:
        result = predict_single(model_id, db, property_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found. Models are stored in memory and lost on server restart.",
        )

    return SinglePredictionResponse(**result)
