from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProcurementRecommendationCreate(BaseModel):
    part_id: int
    recommended_quantity: int = Field(..., ge=0)
    unit_cost: float = Field(..., ge=0.0)
    estimated_cost: Optional[float] = None
    priority: Literal["Critical", "High", "Medium", "Low"] = "High"
    reason: Optional[str] = None
    model_name: str = "PuLP-Procurement-Optimizer"


class ProcurementRecommendationBatchCreate(BaseModel):
    recommendations: List[ProcurementRecommendationCreate]


class ProcurementRecommendationResponse(BaseModel):
    id: int
    part_id: int
    part_name: Optional[str] = None
    part_number: Optional[str] = None
    sku: Optional[str] = None
    part: Optional[str] = None  # frontend alias
    category: Optional[str] = None
    recommended_quantity: int
    quantity: Optional[int] = None  # frontend alias
    unit_cost: float
    unit_price: Optional[float] = None  # frontend alias
    estimated_cost: float
    total_cost: Optional[float] = None  # frontend alias
    priority: str
    reason: Optional[str] = None
    model_name: str
    primary_supplier: Optional[str] = None
    supplier: Optional[str] = None  # frontend alias
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PuLPOptimizationInputItem(BaseModel):
    part_id: int
    part_number: Optional[str] = None
    sku: str
    part_name: Optional[str] = None
    name: str
    category: str
    criticality: str
    current_inventory: int
    reorder_point: int
    safety_stock: int
    max_stock: int
    forecast_demand: float
    vendor_id: Optional[int] = None
    supplier_id: Optional[int] = None
    vendor_name: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_unit_cost: float
    lead_time_days: int
    minimum_order_quantity: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PuLPOptimizationInputResponse(BaseModel):
    depot: str
    generated_at: datetime
    items: List[PuLPOptimizationInputItem]


class ProcurementOptimizationRequest(BaseModel):
    total_budget: Optional[float] = Field(None, ge=0.0, description="Optional total procurement budget cap in INR")
    parts_filter: Optional[List[int]] = Field(None, description="Optional list of specific part_ids to optimize")
    target_service_level: Optional[float] = Field(0.95, ge=0.5, le=1.0)


class OptimizedOrderItem(BaseModel):
    part_id: int
    part_number: str
    part_name: str
    category: str
    criticality: str
    current_inventory: int
    safety_stock: int
    reorder_point: int
    forecast_demand: float
    recommended_order_quantity: int
    unit_cost: float
    total_cost: float
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    lead_time_days: int
    minimum_order_quantity: int
    priority: str
    reason: str


class ProcurementOptimizationResponse(BaseModel):
    status: str = "optimal"
    optimization_engine: str = "PuLP Linear Programming"
    generated_at: str
    total_parts_analyzed: int
    total_parts_to_order: int
    total_recommended_spend: float
    budget_cap: Optional[float] = None
    recommendations: List[OptimizedOrderItem]
