from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PartBase(BaseModel):
    part_number: Optional[str] = Field(None, min_length=2, max_length=100, description="Part / SKU number")
    sku: Optional[str] = Field(None, min_length=2, max_length=100, description="Legacy alias for part_number")
    part_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Official part name")
    name: Optional[str] = Field(None, min_length=2, max_length=255, description="Legacy alias for part_name")
    category: str = Field(..., min_length=2, max_length=100, description="Component category")
    sub_category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, description="Detailed description of the part")
    unit_of_measure: Optional[str] = Field("Each", max_length=50)
    criticality: str = Field("Essential", description="Criticality: Critical, High, Medium, Low / VED")
    vehicle_system: Optional[str] = Field(None, max_length=100)
    standard_cost: Optional[float] = Field(None, ge=0.0, description="Standard cost per unit in INR")
    unit_cost: Optional[float] = Field(None, ge=0.0, description="Legacy alias for standard_cost")
    minimum_order_quantity: Optional[int] = Field(1, ge=1)
    reorder_point: Optional[int] = Field(10, ge=0)
    safety_stock: Optional[int] = Field(5, ge=0)
    lead_time_days: Optional[int] = Field(7, ge=1)
    annual_demand: Optional[float] = Field(0.0, ge=0.0)
    active_status: Optional[str] = Field("Active", max_length=50)

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pn = data.get("part_number") or data.get("sku")
            if pn:
                data["part_number"] = pn
                data["sku"] = pn

            pname = data.get("part_name") or data.get("name")
            if pname:
                data["part_name"] = pname
                data["name"] = pname

            cost = data.get("standard_cost") if data.get("standard_cost") is not None else data.get("unit_cost")
            if cost is not None:
                data["standard_cost"] = float(cost)
                data["unit_cost"] = float(cost)
            else:
                data["standard_cost"] = 0.0
                data["unit_cost"] = 0.0
        return data


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    part_number: Optional[str] = Field(None, min_length=2, max_length=100)
    sku: Optional[str] = Field(None, min_length=2, max_length=100)
    part_name: Optional[str] = Field(None, min_length=2, max_length=255)
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    category: Optional[str] = Field(None, min_length=2, max_length=100)
    sub_category: Optional[str] = None
    description: Optional[str] = None
    unit_of_measure: Optional[str] = None
    criticality: Optional[str] = None
    vehicle_system: Optional[str] = None
    standard_cost: Optional[float] = Field(None, ge=0.0)
    unit_cost: Optional[float] = Field(None, ge=0.0)
    minimum_order_quantity: Optional[int] = Field(None, ge=1)
    reorder_point: Optional[int] = Field(None, ge=0)
    safety_stock: Optional[int] = Field(None, ge=0)
    lead_time_days: Optional[int] = Field(None, ge=1)
    annual_demand: Optional[float] = Field(None, ge=0.0)
    active_status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "sku" in data and "part_number" not in data:
                data["part_number"] = data["sku"]
            if "name" in data and "part_name" not in data:
                data["part_name"] = data["name"]
            if "unit_cost" in data and "standard_cost" not in data:
                data["standard_cost"] = data["unit_cost"]
        return data


class PartResponse(PartBase):
    part_id: int
    id: int  # frontend compatibility alias
    created_date: Optional[datetime] = None
    created_at: Optional[datetime] = None  # frontend alias

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InventoryUpdate(BaseModel):
    current_stock: Optional[int] = Field(None, ge=0, description="Current on-hand physical stock")
    quantity: Optional[int] = Field(None, ge=0, description="Frontend alias for current_stock")
    reserved_stock: Optional[int] = Field(None, ge=0)
    available_stock: Optional[int] = Field(None, ge=0)
    stock_in_transit: Optional[int] = Field(None, ge=0)
    reorder_point: Optional[int] = Field(None, ge=0)
    safety_stock: Optional[int] = Field(None, ge=0)
    maximum_stock: Optional[int] = Field(None, ge=0)
    max_stock: Optional[int] = Field(None, ge=0, description="Frontend alias for maximum_stock")
    average_unit_cost: Optional[float] = Field(None, ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "quantity" in data and "current_stock" not in data:
                data["current_stock"] = data["quantity"]
            if "max_stock" in data and "maximum_stock" not in data:
                data["maximum_stock"] = data["max_stock"]
        return data


class InventoryItemResponse(BaseModel):
    inventory_id: Optional[int] = None
    id: Optional[int] = None  # alias for inventory_id
    part_id: int
    part_number: Optional[str] = None
    sku: str  # alias for frontend
    part_name: Optional[str] = None
    name: str  # alias for frontend
    part: str  # alias for frontend
    category: str
    sub_category: Optional[str] = None
    criticality: str
    standard_cost: Optional[float] = 0.0
    unit_cost: float  # alias for frontend
    average_unit_cost: Optional[float] = 0.0
    current_stock: int
    quantity: int  # alias for frontend
    currentStock: int  # alias for frontend
    reserved_stock: Optional[int] = 0
    available_stock: Optional[int] = 0
    stock_in_transit: Optional[int] = 0
    reorder_point: int
    reorderPoint: int  # alias for frontend
    safety_stock: int
    safetyStock: int  # alias for frontend
    maximum_stock: int
    max_stock: int  # alias for frontend
    maxStock: int  # alias for frontend
    inventory_value: Optional[float] = 0.0
    last_receipt_date: Optional[datetime] = None
    last_issue_date: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    updated_at: Optional[datetime] = None  # alias for frontend
    depot: str = "KSRTC Central Stores"
    status: str  # Healthy, Warning, Critical
    stockoutRisk: str  # Low, Medium, High
    daysOfSupply: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InventoryTransactionCreate(BaseModel):
    part_id: int
    transaction_type: str  # PO_RECEIPT, CONSUMPTION, ADJUSTMENT, RETURN
    quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None


class InventoryTransactionResponse(BaseModel):
    id: int
    part_id: int
    part_name: Optional[str] = None
    part_number: Optional[str] = None
    sku: Optional[str] = None
    transaction_type: str
    quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    transaction_date: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(BaseModel):
    status: str = "ok"
    database: str = "connected"
    depot: str = "KSRTC Central Stores"
    timestamp: datetime

