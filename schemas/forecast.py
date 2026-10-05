from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DemandHistoryCreate(BaseModel):
    part_id: int
    date: date
    quantity_consumed: int = Field(..., ge=0)
    depot: str = "KSRTC Central Stores"


class DemandHistoryBatchCreate(BaseModel):
    records: List[DemandHistoryCreate]


class DemandHistoryResponse(BaseModel):
    id: int
    part_id: int
    part_number: Optional[str] = None
    sku: Optional[str] = None
    part_name: Optional[str] = None
    date: date
    quantity_consumed: int
    depot: str

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ForecastCreate(BaseModel):
    part_id: int
    forecast_date: date
    forecast_quantity: float = Field(..., ge=0.0)
    model_name: str = "XGBoost-Demand-Predictor"
    model_version: str = "v1.0"


class ForecastBatchCreate(BaseModel):
    records: List[ForecastCreate]


class ForecastResponse(BaseModel):
    id: int
    part_id: int
    part_name: Optional[str] = None
    part_number: Optional[str] = None
    sku: Optional[str] = None
    forecast_date: date
    forecast_quantity: float
    model_name: str
    model_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ForecastPoint(BaseModel):
    date: str
    forecast_quantity: float


class ForecastEndpointResponse(BaseModel):
    part_id: str
    model: str = "XGBoost"
    forecast_horizon: int = 30
    forecast: List[Dict[str, Any]] = Field(default_factory=list)
    total_forecast: float = 0.0
    mape: float = 0.0
    mae: Optional[float] = None
    rmse: Optional[float] = None


class ForecastPredictRequest(BaseModel):
    part_id: int
    forecast_horizon: Optional[int] = Field(30, ge=1, le=365)

