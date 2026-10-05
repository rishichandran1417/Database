"""
Demand History & ML Forecasting API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from utils.validation import verify_api_key
from services.forecasting_service import ForecastingService
from schemas.forecast import (
    DemandHistoryBatchCreate,
    DemandHistoryCreate,
    DemandHistoryResponse,
    ForecastBatchCreate,
    ForecastCreate,
    ForecastEndpointResponse,
    ForecastResponse,
)

router = APIRouter(tags=["Demand Forecasting"])


@router.get("/demand-history", response_model=List[DemandHistoryResponse])
def get_demand_history(
    part_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    return ForecastingService.get_demand_history(part_id, start_date, end_date, limit)


@router.post("/demand-history", response_model=DemandHistoryResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def record_demand(payload: DemandHistoryCreate):
    return ForecastingService.record_demand(payload)


@router.post("/demand-history/batch", status_code=201, dependencies=[Depends(verify_api_key)])
def record_demand_batch(payload: DemandHistoryBatchCreate):
    return ForecastingService.record_demand_batch(payload)


@router.get("/forecast", tags=["Demand Forecasting"])
@router.get("/forecasts/probe", tags=["Demand Forecasting"], include_in_schema=False)
def probe_ml_forecasting_service():
    """Lightweight ML Forecasting Service connection and health probe."""
    return ForecastingService.get_ml_service_health()


@router.get("/forecasts", response_model=List[ForecastResponse])
def get_forecasts(
    part_id: Optional[int] = None,
    model_name: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    return ForecastingService.get_forecasts(part_id, model_name, limit)


@router.get("/forecasts/{part_id}", response_model=ForecastEndpointResponse)
@router.get("/forecast/{part_id}", response_model=ForecastEndpointResponse)
@router.post("/forecast/{part_id}", response_model=ForecastEndpointResponse)
def get_forecast_for_part(part_id: int, forecast_horizon: int = Query(30, ge=1, le=365)):

    """
    Generates 30-day XGBoost demand forecast for specified part_id.
    Returns structured JSON:
    {
      "part_id": "...",
      "model": "XGBoost",
      "forecast_horizon": 30,
      "forecast": [...],
      "total_forecast": ...,
      "mape": ...
    }
    """
    return ForecastingService.generate_part_forecast(part_id, forecast_horizon)


@router.post("/forecasts", status_code=201, dependencies=[Depends(verify_api_key)])
def store_forecasts(payload: ForecastCreate | ForecastBatchCreate):
    items = [payload] if isinstance(payload, ForecastCreate) else payload.records
    from database.connection import get_db_connection
    with get_db_connection() as conn:
        with conn.transaction():
            count = 0
            for f in items:
                conn.execute(
                    """INSERT INTO forecasts (part_id, forecast_date, forecast_quantity, model_name, model_version)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (f.part_id, f.forecast_date, f.forecast_quantity, f.model_name, f.model_version),
                )
                count += 1
            return {"status": "ok", "forecasts_stored": count}
