from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


# ==========================================
# 1. Parts Models
# ==========================================
class PartBase(BaseModel):
    sku: str = Field(..., min_length=2, max_length=100, description="Unique SKU code")
    name: str = Field(..., min_length=2, max_length=255, description="Part name")
    category: str = Field(..., min_length=2, max_length=100, description="Component category")
    description: Optional[str] = Field(None, description="Detailed description of the part")
    unit_cost: float = Field(0.0, ge=0.0, description="Standard cost per unit in INR")
    criticality: str = Field("Essential", description="Criticality: Critical, High, Medium, Low / VED")


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    sku: Optional[str] = Field(None, min_length=2, max_length=100)
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    category: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    unit_cost: Optional[float] = Field(None, ge=0.0)
    criticality: Optional[str] = None


class PartResponse(PartBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. Inventory Models
# ==========================================
class InventoryUpdate(BaseModel):
    quantity: Optional[int] = Field(None, ge=0, description="Current on-hand stock quantity")
    reorder_point: Optional[int] = Field(None, ge=0, description="Reorder trigger level")
    safety_stock: Optional[int] = Field(None, ge=0, description="Minimum buffer stock")
    max_stock: Optional[int] = Field(None, ge=0, description="Depot maximum storage capacity")


class InventoryItemResponse(BaseModel):
    id: Optional[int] = None
    part_id: int
    sku: str
    name: str
    part: str  # alias for frontend compatibility
    category: str
    criticality: str
    unit_cost: float
    quantity: int
    currentStock: int  # alias for frontend
    reorder_point: int
    reorderPoint: int  # alias for frontend
    safety_stock: int
    safetyStock: int  # alias for frontend
    max_stock: int
    maxStock: int  # alias for frontend
    depot: str = "KSRTC Central Depot, Thiruvananthapuram"
    status: str  # Healthy, Warning, Critical
    stockoutRisk: str  # Low, Medium, High
    daysOfSupply: Optional[int] = 0
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. Suppliers Models
# ==========================================
class SupplierBase(BaseModel):
    supplier_code: str = Field(..., min_length=2, max_length=100)
    supplier_name: str = Field(..., min_length=2, max_length=255)
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    lead_time_days: int = Field(7, ge=1, description="Average lead time in calendar days")
    status: str = Field("Active", description="Active, Inactive, Blocked")


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    lead_time_days: Optional[int] = Field(None, ge=1)
    status: Optional[str] = None


class SupplierResponse(SupplierBase):
    id: int
    # Frontend aliases
    name: str
    avgLeadTimeDays: int
    contactEmail: Optional[str] = None
    contactPhone: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. Supplier Parts Models
# ==========================================
class SupplierPartCreate(BaseModel):
    supplier_id: int
    part_id: int
    supplier_unit_cost: float = Field(..., ge=0.0)
    lead_time_days: int = Field(..., ge=1)
    minimum_order_quantity: int = Field(1, ge=1)


class SupplierPartResponse(BaseModel):
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    supplier_code: Optional[str] = None
    part_id: int
    part_name: Optional[str] = None
    sku: Optional[str] = None
    supplier_unit_cost: float
    lead_time_days: int
    minimum_order_quantity: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. Purchase Order Models
# ==========================================
class PurchaseOrderItemCreate(BaseModel):
    part_id: int
    quantity: int = Field(..., gt=0)
    unit_cost: float = Field(..., ge=0.0)


class PurchaseOrderItemResponse(BaseModel):
    id: int
    purchase_order_id: int
    part_id: int
    part_name: Optional[str] = None
    sku: Optional[str] = None
    quantity: int
    unit_cost: float
    received_quantity: int
    total_cost: float
    # Frontend aliases
    part: Optional[str] = None
    unitPrice: Optional[float] = None
    receivedQuantity: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCreate(BaseModel):
    po_number: Optional[str] = Field(None, description="Optional custom PO Number (auto-generated if omitted)")
    supplier_id: Optional[int] = None
    supplier: Optional[str] = None  # name or code
    order_date: Optional[datetime] = None
    expected_date: Optional[datetime] = None
    items: List[PurchaseOrderItemCreate] = Field(default_factory=list)
    # Simple single-item shortcut for legacy compatibility
    part_id: Optional[int] = None
    quantity: Optional[int] = None
    unit_cost: Optional[float] = None


class PurchaseOrderUpdate(BaseModel):
    supplier_id: Optional[int] = None
    expected_date: Optional[datetime] = None
    status: Optional[str] = None


class PurchaseOrderStatusUpdate(BaseModel):
    status: Literal["Draft", "draft", "Ordered", "ordered", "Received", "received", "Cancelled", "cancelled"]


class PurchaseOrderResponse(BaseModel):
    id: int
    po_number: str
    poNumber: str  # frontend alias
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier: Optional[str] = None  # frontend alias
    depot: str = "KSRTC Central Depot, Thiruvananthapuram"
    status: str
    order_date: Optional[datetime] = None
    poDate: Optional[str] = None  # frontend alias
    expected_date: Optional[datetime] = None
    expectedDelivery: Optional[str] = None  # frontend alias
    received_date: Optional[datetime] = None
    total_value: float
    total: float  # frontend alias
    created_at: datetime
    items: List[PurchaseOrderItemResponse] = Field(default_factory=list)
    lines: List[PurchaseOrderItemResponse] = Field(default_factory=list)  # frontend alias

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. Inventory Transactions Models
# ==========================================
class InventoryTransactionCreate(BaseModel):
    part_id: int
    transaction_type: Literal["PO_RECEIPT", "CONSUMPTION", "ADJUSTMENT", "RETURN"]
    quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None


class InventoryTransactionResponse(BaseModel):
    id: int
    part_id: int
    part_name: Optional[str] = None
    sku: Optional[str] = None
    transaction_type: str
    quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    transaction_date: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 7. Demand History Models
# ==========================================
class DemandHistoryCreate(BaseModel):
    part_id: int
    date: date
    quantity_consumed: int = Field(..., ge=0)
    depot: str = "KSRTC Central Depot, Thiruvananthapuram"


class DemandHistoryBatchCreate(BaseModel):
    records: List[DemandHistoryCreate]


class DemandHistoryResponse(BaseModel):
    id: int
    part_id: int
    sku: Optional[str] = None
    part_name: Optional[str] = None
    date: date
    quantity_consumed: int
    depot: str

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 8. Forecasts Models
# ==========================================
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
    sku: Optional[str] = None
    forecast_date: date
    forecast_quantity: float
    model_name: str
    model_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 9. Procurement Recommendations Models (PuLP)
# ==========================================
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

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 10. Model Runs Models
# ==========================================
class ModelRunCreate(BaseModel):
    model_name: str
    model_version: str
    status: Literal["SUCCESS", "RUNNING", "FAILED"] = "SUCCESS"
    metrics_json: Dict[str, Any] = Field(default_factory=dict)


class ModelRunResponse(BaseModel):
    id: int
    model_name: str
    model_version: str
    run_date: datetime
    status: str
    metrics_json: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 11. Optimization & AI Analytics Input Models
# ==========================================
class PuLPOptimizationInputItem(BaseModel):
    part_id: int
    sku: str
    name: str
    category: str
    criticality: str
    current_inventory: int
    reorder_point: int
    safety_stock: int
    max_stock: int
    forecast_demand: float
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_unit_cost: float
    lead_time_days: int
    minimum_order_quantity: int


class PuLPOptimizationInputResponse(BaseModel):
    depot: str
    generated_at: datetime
    items: List[PuLPOptimizationInputItem]


# ==========================================
# 12. Health Response
# ==========================================
class HealthResponse(BaseModel):
    status: str = "ok"
    database: str = "connected"
    depot: str = "KSRTC Central Depot, Thiruvananthapuram"
    timestamp: datetime
