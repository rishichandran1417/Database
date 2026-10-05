"""
Training pipeline for XGBoost / LightGBM time-series demand forecasting model.
Uses time-based train/validation split (no random shuffle) and saves trained model artifact.
"""

import os
import joblib
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from database.connection import get_db_connection
from ml.forecasting.features import FEATURE_COLUMNS, build_time_series_features
from ml.forecasting.evaluation import evaluate_forecast

logger = logging.getLogger("ksrtc_backend.ml.forecasting.train")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODEL_DIR, "xgboost_demand_model.joblib")


def fetch_historical_demand_df() -> pd.DataFrame:
    """Fetches all historical consumption data from demand_history table."""
    try:
        query = """
            SELECT part_id, date, quantity_consumed, depot 
            FROM demand_history 
            ORDER BY date ASC, part_id ASC
        """
        with get_db_connection() as conn:
            rows = conn.execute(query).fetchall()
            if not rows:
                return pd.DataFrame(columns=["part_id", "date", "quantity_consumed", "depot"])
            return pd.DataFrame([dict(r) for r in rows])
    except Exception as e:
        logger.warning(f"Could not fetch demand history from DB ({e}); returning empty DataFrame.")
        return pd.DataFrame(columns=["part_id", "date", "quantity_consumed", "depot"])



def train_forecasting_model(val_split_ratio: float = 0.2) -> dict:
    """
    Trains an XGBoost time-series demand forecasting model using historical demand data.
    Uses time-based split for validation (chronological cutoff, no random shuffle).
    Saves model artifact under ml/forecasting/models/xgboost_demand_model.joblib.
    """
    logger.info("Starting demand forecasting model training...")
    df_raw = fetch_historical_demand_df()
    if df_raw.empty or len(df_raw) < 10:
        logger.warning("Insufficient historical demand data to train ML model. Creating fallback predictor.")
        return {"status": "skipped", "reason": "Insufficient data (minimum 10 records required)"}

    # Build feature dataset
    df_feat = build_time_series_features(df_raw)

    # Time-based split: sort chronologically and take last val_split_ratio proportion as validation
    df_feat = df_feat.sort_values("date").reset_index(drop=True)
    split_idx = int(len(df_feat) * (1 - val_split_ratio))
    
    train_df = df_feat.iloc[:split_idx]
    val_df = df_feat.iloc[split_idx:]

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["quantity_consumed"]
    X_val = val_df[FEATURE_COLUMNS]
    y_val = val_df["quantity_consumed"]

    # Model initialization (XGBoost with LightGBM fallback)
    model = None
    model_name = "XGBoost"
    
    try:
        import xgboost as xgb
        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)
    except Exception as e:
        logger.warning(f"XGBoost training failed ({e}); falling back to RandomForest.")
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
        model.fit(X_train, y_train)
        model_name = "RandomForest"

    # Evaluation on time-series validation set
    y_pred = model.predict(X_val)
    y_pred = np.maximum(0, y_pred)  # ensure non-negative prediction
    metrics = evaluate_forecast(y_val.to_numpy(), y_pred)
    metrics["model_name"] = model_name
    metrics["train_size"] = len(train_df)
    metrics["val_size"] = len(val_df)

    logger.info(f"Model trained successfully ({model_name}). Metrics: {metrics}")

    # Save trained model artifact
    artifact = {
        "model": model,
        "model_name": model_name,
        "model_version": "v1.0",
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(artifact, MODEL_PATH)
    logger.info(f"Saved trained model to {MODEL_PATH}")

    # Record model run in DB if possible
    try:
        import json
        with get_db_connection() as conn:
            with conn.transaction():
                conn.execute(
                    """INSERT INTO model_runs (model_name, model_version, status, metrics_json)
                       VALUES (%s, %s, 'SUCCESS', %s::jsonb)""",
                    (f"{model_name}-Demand-Predictor", "v1.0", json.dumps(metrics)),
                )
    except Exception as db_err:
        logger.debug(f"Failed to record model_run: {db_err}")

    return metrics


if __name__ == "__main__":
    train_forecasting_model()
