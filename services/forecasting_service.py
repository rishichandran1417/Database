"""
Forecasting Service bridging database demand history and ML forecasting engine.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import HTTPException

from database.connection import get_db_connection
from database.queries import SELECT_DEMAND_HISTORY, UPSERT_DEMAND_HISTORY, SELECT_FORECASTS, INSERT_FORECAST
from schemas.forecast import (
    DemandHistoryCreate,
    DemandHistoryBatchCreate,
    DemandHistoryResponse,
    ForecastCreate,
    ForecastBatchCreate,
    ForecastResponse,
    ForecastEndpointResponse,
)
from ml.forecasting.predict import predict_demand_for_part, load_model_artifact, MODEL_PATH
import os

logger = logging.getLogger("ksrtc_backend.services.forecasting")


class ForecastingService:
    @staticmethod
    def get_ml_service_health() -> Dict[str, Any]:
        """Lightweight health probe endpoint for ML forecasting service connection check."""
        try:
            import xgboost
            ml_available = True
        except ImportError:
            ml_available = False

        artifact = load_model_artifact()
        model_name = artifact.get("model_name", "XGBoost")
        is_loaded = (artifact.get("model") is not None) or os.path.exists(MODEL_PATH) or ml_available
        return {
            "status": "ok",
            "service": "ML Forecasting Service",
            "model": model_name,
            "model_loaded": bool(is_loaded),
        }


    @staticmethod
    def get_demand_history(part_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 1000) -> List[dict]:

        query = SELECT_DEMAND_HISTORY
        params = []
        if part_id:
            query += " AND dh.part_id = %s"
            params.append(part_id)
        if start_date:
            query += " AND dh.date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND dh.date <= %s"
            params.append(end_date)
        query += " ORDER BY dh.date DESC, p.part_name ASC LIMIT %s"
        params.append(limit)

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def record_demand(payload: DemandHistoryCreate) -> dict:
        with get_db_connection() as conn:
            with conn.transaction():
                part = conn.execute("SELECT part_id, part_number, part_name FROM parts WHERE part_id = %s", (payload.part_id,)).fetchone()
                if not part:
                    raise HTTPException(status_code=404, detail="Part not found.")

                row = conn.execute(
                    UPSERT_DEMAND_HISTORY,
                    (payload.part_id, payload.date, payload.quantity_consumed, payload.depot),
                ).fetchone()

                item = dict(row)
                item["part_number"] = part["part_number"]
                item["sku"] = part["part_number"]
                item["part_name"] = part["part_name"]
                return item

    @staticmethod
    def record_demand_batch(payload: DemandHistoryBatchCreate) -> dict:
        with get_db_connection() as conn:
            with conn.transaction():
                inserted_count = 0
                for rec in payload.records:
                    conn.execute(
                        UPSERT_DEMAND_HISTORY,
                        (rec.part_id, rec.date, rec.quantity_consumed, rec.depot),
                    )
                    inserted_count += 1
                return {"status": "ok", "records_processed": inserted_count}

    @staticmethod
    def get_forecasts(part_id: Optional[int] = None, model_name: Optional[str] = None, limit: int = 200) -> List[dict]:
        query = SELECT_FORECASTS
        params = []
        if part_id:
            query += " AND f.part_id = %s"
            params.append(part_id)
        if model_name:
            query += " AND LOWER(f.model_name) = LOWER(%s)"
            params.append(model_name)
        query += " ORDER BY f.forecast_date ASC, p.part_name ASC LIMIT %s"
        params.append(limit)

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def generate_part_forecast(part_id: int, forecast_horizon: int = 30) -> Dict[str, Any]:
        """Generates 30-day XGBoost demand forecast for a single part using ML engine."""
        return predict_demand_for_part(part_id, forecast_horizon=forecast_horizon)
