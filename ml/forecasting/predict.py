"""
Inference module for ML demand forecasting.
Loads trained XGBoost model from ml/forecasting/models/ and generates 30-day demand predictions.
Does NOT retrain on every API request.
"""

import os
import joblib
import logging
from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Any
import pandas as pd
import numpy as np

from database.connection import get_db_connection
from ml.forecasting.features import FEATURE_COLUMNS, build_time_series_features
from ml.forecasting.train import MODEL_PATH, train_forecasting_model

logger = logging.getLogger("ksrtc_backend.ml.forecasting.predict")

_cached_model_artifact: Dict[str, Any] | None = None


def load_model_artifact() -> Dict[str, Any]:
    """Loads and caches the trained ML model artifact."""
    global _cached_model_artifact

    if _cached_model_artifact is not None:
        return _cached_model_artifact

    if not os.path.exists(MODEL_PATH):
        logger.info("No pre-trained model found at %s. Triggering one-time model training...", MODEL_PATH)
        train_forecasting_model()

    if os.path.exists(MODEL_PATH):
        try:
            _cached_model_artifact = joblib.load(MODEL_PATH)
            logger.info("Successfully loaded ML model artifact (%s)", _cached_model_artifact.get("model_name", "XGBoost"))
            return _cached_model_artifact
        except Exception as e:
            logger.error("Failed to load model file: %s. Using heuristic predictor fallback.", e)

    return {"model": None, "model_name": "Heuristic-Moving-Average", "metrics": {"mape": 0.0}}


def predict_demand_for_part(part_id: int, forecast_horizon: int = 30) -> Dict[str, Any]:
    """
    Generates forecast_horizon day demand predictions for a given part_id using the loaded ML model.
    If historical data is insufficient (< 7 records), returns explicit status instead of a misleading fallback.
    """
    artifact = load_model_artifact()
    model = artifact.get("model")
    model_name = artifact.get("model_name", "XGBoost")
    metrics = artifact.get("metrics", {})
    mape = float(metrics.get("mape", 0.0)) if "mape" in metrics else None
    wape = float(metrics.get("wape", 0.0)) if "wape" in metrics else None
    smape = float(metrics.get("smape", 0.0)) if "smape" in metrics else None
    mae = float(metrics.get("mae", 0.0)) if "mae" in metrics else None
    rmse = float(metrics.get("rmse", 0.0)) if "rmse" in metrics else None
    bias = float(metrics.get("bias", 0.0)) if "bias" in metrics else None

    # Fetch recent historical demand for this part
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT part_id, date, quantity_consumed, depot 
                   FROM demand_history 
                   WHERE part_id = %s 
                   ORDER BY date ASC""",
                (part_id,),
            ).fetchall()
        history_df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    except Exception as e:
        logger.debug("Could not fetch demand history for part %s from DB (%s).", part_id, e)
        history_df = pd.DataFrame()

    if history_df.empty or len(history_df) < 7 or model is None:
        return {
            "status": "insufficient_history",
            "part_id": str(part_id),
            "message": f"Insufficient historical demand data for ML forecasting (minimum 7 records required, found {len(history_df)}).",
            "historical_records": len(history_df),
            "forecast_horizon": forecast_horizon,
            "model": model_name,
            "forecast": [],
            "total_forecast": 0.0,
            "mape": None,
            "wape": None,
            "smape": None,
            "mae": None,
            "rmse": None,
            "bias": None,
        }

    today = date.today()
    forecast_list: List[Dict[str, Any]] = []
    total_forecast = 0.0

    # Recursive auto-regressive multi-step forecasting
    df_sim = history_df.copy()
    df_sim["date"] = pd.to_datetime(df_sim["date"])

    for step in range(1, forecast_horizon + 1):
        next_date = today + timedelta(days=step)
        # Add dummy placeholder for next_date
        temp_row = pd.DataFrame([{
            "part_id": part_id,
            "date": pd.to_datetime(next_date),
            "quantity_consumed": 0,
            "depot": "KSRTC Central Stores",
        }])
        df_curr = pd.concat([df_sim, temp_row], ignore_index=True)
        df_feat = build_time_series_features(df_curr)

        latest_row = df_feat.iloc[[-1]]
        X_input = latest_row[FEATURE_COLUMNS]

        pred_qty = float(np.maximum(0, model.predict(X_input)[0]))
        pred_qty_rounded = round(pred_qty, 2)

        forecast_list.append({
            "date": next_date.strftime("%Y-%m-%d"),
            "forecast_quantity": pred_qty_rounded,
        })
        total_forecast += pred_qty_rounded

        # Update simulated history with predicted value
        df_sim = pd.concat([
            df_sim,
            pd.DataFrame([{
                "part_id": part_id,
                "date": pd.to_datetime(next_date),
                "quantity_consumed": pred_qty_rounded,
                "depot": "KSRTC Central Stores",
            }]),
        ], ignore_index=True)

    total_forecast = float(round(total_forecast, 2))

    return {
        "status": "success",
        "part_id": str(part_id),
        "historical_records": len(history_df),
        "model": model_name,
        "forecast_horizon": forecast_horizon,
        "forecast": forecast_list,
        "total_forecast": total_forecast,
        "mape": mape,
        "wape": wape,
        "smape": smape,
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
    }

