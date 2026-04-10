"""Model training for property price prediction.

Supports LightGBM and XGBoost with temporal or random train/test splits.
Trained models are stored in-memory (not persistent).
"""

import logging
import math
import uuid
from typing import Any, Callable, Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb

# Type for progress callbacks: (progress_0_to_1, detail_message) -> None
ProgressCallback = Callable[[float, str], None]

logger = logging.getLogger(__name__)

# In-memory store: {model_id: {model, features, model_type, target, ...}}
_model_store: dict[str, dict[str, Any]] = {}

# Default hyperparameters
_LGB_DEFAULTS = {
    "objective": "regression",
    "metric": "rmse",
    "num_leaves": 31,
    "learning_rate": 0.1,
    "linear_tree": False,
    "verbose": -1,
}

_XGB_DEFAULTS = {
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "max_depth": 6,
    "learning_rate": 0.1,
    "verbosity": 0,
}

_NUM_ROUNDS = 100
_BATCH_SIZE = 100_000


def train_model(
    df: pd.DataFrame,
    target: str,
    feature_names: list[str],
    model_type: str,
    split_strategy: str,
    split_params: dict,
    hyperparameters: Optional[dict] = None,
    log_transform: bool = False,
    max_train_rows: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """Train a model and return results.

    Returns dict with model_id, metrics, feature_importances, predictions,
    train_size, test_size.
    """
    def _progress(pct: float, msg: str) -> None:
        if on_progress:
            on_progress(pct, msg)

    # Only keep features that exist in the DataFrame
    available_features = [f for f in feature_names if f in df.columns]
    if not available_features:
        raise ValueError("No valid features found in the dataset")

    # Identify categorical features for the model
    cat_features = [
        f for f in available_features
        if df[f].dtype.name == "category"
    ]

    _progress(0.05, "Splitting data")

    # Split data
    train_df, test_df = _split_data(df, split_strategy, split_params, max_train_rows)

    if len(train_df) < 5:
        raise ValueError(f"Training set too small: {len(train_df)} rows")
    if len(test_df) < 2:
        raise ValueError(f"Test set too small: {len(test_df)} rows")

    X_train = train_df[available_features]
    y_train = train_df[target]
    X_test = test_df[available_features]
    y_test = test_df[target]

    # Log-transform target if requested
    if log_transform:
        y_train = np.log1p(y_train)

    _progress(0.10, f"Training {model_type} on {len(X_train):,} rows")

    # Train — progress from 0.10 to 0.85
    if model_type == "lightgbm":
        model, importances = _train_lgb(
            X_train, y_train, cat_features, hyperparameters, on_progress,
        )
        y_pred_raw = model.predict(X_test)
    else:
        model, importances = _train_xgb(
            X_train, y_train, cat_features, hyperparameters, on_progress,
        )
        dtest = xgb.DMatrix(X_test, enable_categorical=True)
        y_pred_raw = model.predict(dtest)

    _progress(0.90, "Computing metrics")

    # Inverse-transform predictions for metrics and output
    y_pred = np.expm1(y_pred_raw) if log_transform else y_pred_raw

    # Metrics (always on original scale)
    metrics = _compute_metrics(y_test.values, y_pred)

    # Feature importances (normalized to %)
    total_imp = sum(importances.values()) if importances else 0
    feat_imp = [
        {"feature": f, "importance": round(v / total_imp * 100, 2) if total_imp > 0 else 0.0}
        for f, v in sorted(importances.items(), key=lambda x: -x[1])
    ]

    # Predictions with metadata (original scale)
    predictions = []
    for i, (_idx, row) in enumerate(test_df.iterrows()):
        predictions.append({
            "actual": float(y_test.iloc[i]),
            "predicted": float(y_pred[i]),
            "residual": float(y_pred[i] - y_test.iloc[i]),
            "property_id": int(row.get("property_id", 0)),
            "address": str(row.get("address", "")),
        })

    _progress(0.95, "Storing model")

    # Store model
    model_id = str(uuid.uuid4())[:8]
    _model_store[model_id] = {
        "model": model,
        "features": available_features,
        "model_type": model_type,
        "target": target,
        "categorical_features": cat_features,
        "log_transform": log_transform,
    }

    return {
        "model_id": model_id,
        "metrics": metrics,
        "feature_importances": feat_imp,
        "predictions": predictions,
        "train_size": len(train_df),
        "test_size": len(test_df),
    }


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def _split_data(
    df: pd.DataFrame, strategy: str, params: dict,
    max_train_rows: int | None = None,
) -> tuple:
    """Split DataFrame into train and test sets.

    If max_train_rows is set, the training set is randomly sampled down
    to that size after the split.  This keeps memory and training time
    manageable on very large datasets while still using the full test
    set for evaluation.
    """
    if strategy == "temporal":
        cutoff = params.get("cutoff_date", "2024-01-01")
        if "date_sold_iso" not in df.columns:
            raise ValueError("Temporal split requires date_sold_iso column")
        train = df[df["date_sold_iso"] < cutoff]
        test = df[df["date_sold_iso"] >= cutoff]
    else:
        # Random split
        ratio = float(params.get("test_ratio", 0.2))
        test = df.sample(frac=ratio, random_state=42)
        train = df.drop(test.index)

    # Sub-sample the training set if requested
    if max_train_rows and len(train) > max_train_rows:
        logger.info("Sampling training set: %d → %d rows", len(train), max_train_rows)
        train = train.sample(n=max_train_rows, random_state=42)

    return train, test


# ---------------------------------------------------------------------------
# LightGBM
# ---------------------------------------------------------------------------

def _train_lgb(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cat_features: list[str],
    hyperparameters: Optional[dict],
    on_progress: ProgressCallback | None = None,
) -> tuple:
    """Train a LightGBM model in batches. Returns (model, importances_dict).

    If X_train has more than _BATCH_SIZE rows, training is done
    incrementally: each batch adds boosting rounds on top of the
    previous model, so every row in the training set contributes.
    """
    params = {**_LGB_DEFAULTS}
    if hyperparameters:
        params.update(hyperparameters)

    num_rounds = int(params.pop("n_estimators", _NUM_ROUNDS))
    n_rows = len(X_train)

    if n_rows <= _BATCH_SIZE:
        # Small enough — single pass
        if on_progress:
            on_progress(0.45, "Training single batch")
        dtrain = lgb.Dataset(
            X_train, y_train,
            categorical_feature=cat_features if cat_features else "auto",
            free_raw_data=False,
        )
        model = lgb.train(params, dtrain, num_boost_round=num_rounds)
    else:
        # Batch training — split rounds across batches
        n_batches = (n_rows + _BATCH_SIZE - 1) // _BATCH_SIZE
        rounds_per_batch = max(num_rounds // n_batches, 10)
        indices = np.arange(n_rows)
        np.random.default_rng(42).shuffle(indices)

        model = None
        for i in range(n_batches):
            batch_idx = indices[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
            if on_progress:
                pct = 0.10 + 0.75 * (i / n_batches)
                on_progress(pct, f"Training batch {i + 1}/{n_batches} ({len(batch_idx):,} rows)")
            dtrain = lgb.Dataset(
                X_train.iloc[batch_idx], y_train.iloc[batch_idx],
                categorical_feature=cat_features if cat_features else "auto",
                free_raw_data=False,
            )
            model = lgb.train(
                params, dtrain,
                num_boost_round=rounds_per_batch,
                init_model=model,
            )
            logger.info(
                "LightGBM batch %d/%d: %d rows, %d rounds (total trees: %d)",
                i + 1, n_batches, len(batch_idx), rounds_per_batch,
                model.num_trees(),
            )

    # Feature importances
    imp_values = model.feature_importance(importance_type="gain")
    imp_names = model.feature_name()
    importances = {n: float(v) for n, v in zip(imp_names, imp_values)}

    return model, importances


# ---------------------------------------------------------------------------
# XGBoost
# ---------------------------------------------------------------------------

def _train_xgb(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cat_features: list[str],
    hyperparameters: Optional[dict],
    on_progress: ProgressCallback | None = None,
) -> tuple:
    """Train an XGBoost model in batches. Returns (model, importances_dict).

    If X_train has more than _BATCH_SIZE rows, training is done
    incrementally: each batch adds boosting rounds via xgb_model,
    so every row in the training set contributes.
    """
    params = {**_XGB_DEFAULTS}
    if hyperparameters:
        params.update(hyperparameters)
    # XGBoost needs tree_method=hist for categorical support
    params.setdefault("tree_method", "hist")

    num_rounds = int(params.pop("n_estimators", _NUM_ROUNDS))
    n_rows = len(X_train)

    if n_rows <= _BATCH_SIZE:
        # Small enough — single pass
        if on_progress:
            on_progress(0.45, "Training single batch")
        dtrain = xgb.DMatrix(X_train, y_train, enable_categorical=True)
        model = xgb.train(params, dtrain, num_boost_round=num_rounds)
    else:
        # Batch training — split rounds across batches
        n_batches = (n_rows + _BATCH_SIZE - 1) // _BATCH_SIZE
        rounds_per_batch = max(num_rounds // n_batches, 10)
        indices = np.arange(n_rows)
        np.random.default_rng(42).shuffle(indices)

        model = None
        for i in range(n_batches):
            batch_idx = indices[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
            if on_progress:
                pct = 0.10 + 0.75 * (i / n_batches)
                on_progress(pct, f"Training batch {i + 1}/{n_batches} ({len(batch_idx):,} rows)")
            dtrain = xgb.DMatrix(
                X_train.iloc[batch_idx], y_train.iloc[batch_idx],
                enable_categorical=True,
            )
            model = xgb.train(
                params, dtrain,
                num_boost_round=rounds_per_batch,
                xgb_model=model,
            )
            logger.info(
                "XGBoost batch %d/%d: %d rows, %d rounds",
                i + 1, n_batches, len(batch_idx), rounds_per_batch,
            )

    # Feature importances
    importances = model.get_score(importance_type="gain")
    # Ensure all features are present (XGBoost only returns non-zero)
    for f in X_train.columns:
        if f not in importances:
            importances[f] = 0.0

    return model, importances


# ---------------------------------------------------------------------------
# Metrics (no sklearn dependency)
# ---------------------------------------------------------------------------

def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute R², RMSE, MAE, MAPE."""
    residuals = y_pred - y_true
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))

    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse = float(math.sqrt(np.mean(residuals ** 2)))
    mae = float(np.mean(np.abs(residuals)))

    # MAPE (exclude zeros in actuals)
    mask = y_true != 0
    mape = float(np.mean(np.abs(residuals[mask] / y_true[mask])) * 100) if mask.any() else 0.0

    return {
        "r_squared": round(r_squared, 4),
        "rmse": round(rmse, 2),
        "mae": round(mae, 2),
        "mape": round(mape, 2),
    }
