"""Modelling router — train models and predict property prices."""

import json
import logging
import queue
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..modelling.data_assembly import FEATURE_REGISTRY, TARGETS, assemble_dataset
from ..modelling.predictor import predict_postcode, predict_single
from ..modelling.trainer import train_model
from ..models import Sale
from ..schemas import (
    AvailableFeaturesResponse,
    FeatureInfo,
    PostcodePredictionResponse,
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


@router.post("/train")
def train(request: TrainRequest, db: Session = Depends(get_db)):
    """Train a model, streaming SSE progress events.

    Events:
      event: progress  — {progress: 0-1, detail: "..."}
      event: result    — full TrainResponse JSON
      event: error     — {detail: "..."}
    """
    # Validate inputs up-front (before streaming begins)
    if request.target not in _VALID_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target '{request.target}'. Must be one of: {sorted(_VALID_TARGETS)}",
        )
    if request.model_type not in _VALID_MODEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{request.model_type}'. Must be one of: {sorted(_VALID_MODEL_TYPES)}",
        )
    if not request.features:
        raise HTTPException(status_code=400, detail="At least one feature is required")

    # Queue-based SSE: training runs in a thread, pushes events to the queue.
    # The generator yields from the queue, giving real-time progress updates.
    _SENTINEL = None
    event_q: queue.Queue = queue.Queue()

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def _emit_progress(pct: float, detail: str) -> None:
        event_q.put(_sse("progress", {"progress": round(pct, 3), "detail": detail}))

    def _train_thread():
        try:
            _emit_progress(0.02, "Assembling dataset")
            try:
                df = assemble_dataset(db, request.target, request.features, on_progress=_emit_progress)
            except Exception as e:
                logger.exception("Dataset assembly failed")
                event_q.put(_sse("error", {"detail": f"Dataset assembly failed: {e}"}))
                return

            if df.empty or len(df) < _MIN_TRAINING_ROWS:
                event_q.put(_sse("error", {
                    "detail": f"Insufficient data: {len(df)} rows (minimum {_MIN_TRAINING_ROWS} required)",
                }))
                return

            _emit_progress(0.05, f"Dataset ready: {len(df):,} rows")

            try:
                result = train_model(
                    df=df,
                    target=request.target,
                    feature_names=request.features,
                    model_type=request.model_type,
                    split_strategy=request.split_strategy,
                    split_params=request.split_params,
                    hyperparameters=request.hyperparameters,
                    log_transform=request.log_transform,
                    max_train_rows=request.max_train_rows,
                    on_progress=_emit_progress,
                )
            except ValueError as e:
                event_q.put(_sse("error", {"detail": str(e)}))
                return
            except Exception as e:
                logger.exception("Model training failed")
                event_q.put(_sse("error", {"detail": f"Training failed: {e}"}))
                return

            _emit_progress(1.0, "Complete")
            event_q.put(_sse("result", TrainResponse(**result).model_dump()))
        finally:
            event_q.put(_SENTINEL)

    def generate():
        thread = threading.Thread(target=_train_thread, daemon=True)
        thread.start()
        while True:
            item = event_q.get()
            if item is _SENTINEL:
                break
            yield item

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{model_id}/predict", response_model=SinglePredictionResponse)
def predict(
    model_id: str,
    property_id: int,
    prediction_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Predict the target value for a single property using a trained model."""
    try:
        result = predict_single(model_id, db, property_id, prediction_date)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found. Models are stored in memory and lost on server restart.",
        )

    return SinglePredictionResponse(**result)


@router.get("/{model_id}/predict-postcode", response_model=PostcodePredictionResponse)
def predict_by_postcode(
    model_id: str,
    postcode: str,
    prediction_date: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Predict values for all properties in a given postcode."""
    try:
        results = predict_postcode(
            model_id, db, postcode, limit=min(limit, 200),
            prediction_date=prediction_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found. Models are stored in memory and lost on server restart.",
        )

    return PostcodePredictionResponse(
        postcode=postcode.upper().strip(),
        count=len(results),
        predictions=results,
    )
