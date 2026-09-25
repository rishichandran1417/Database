from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ==========================================
# 1. Parts Models (Actual Neon Schema: parts)
# Columns: part_id, part_number, part_name, category, sub_category,
# description, unit_of_measure, criticality, vehicle_system, standard_cost,
# minimum_order_quantity, reorder_point, safety_stock, lead_time_days,
# annual_demand, active_status, created_date
# ==========================================
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
            # Resolve part_number / sku
            pn = data.get("part_number") or data.get("sku")
            if pn:
                data["part_number"] = pn
                data["sku"] = pn

            # Resolve part_name / name
            pname = data.get("part_name") or data.get("name")
            if pname:
                data["part_name"] = pname
                data["name"] = pname

            # Resolve standard_cost / unit_cost
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


# ==========================================
# 2. Inventory Models (Actual Neon Schema: inventory)
# Columns: inventory_id, part_id, current_stock, reserved_stock,
# available_stock, stock_in_transit, reorder_point, safety_stock,
# maximum_stock, average_unit_cost, inventory_value, last_receipt_date,
# last_issue_date, last_updated
# ==========================================
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


# ==========================================
# 3. Vendors Models (Actual Neon Schema: vendors)
# Columns: vendor_id, vendor_code, vendor_name, city, state, country,
# contact_email, contact_phone, vendor_category, payment_terms_days,
# default_lead_time_days, rating, on_time_delivery_rate, quality_rating,
# active_status, vendor_since
# ==========================================
class VendorBase(BaseModel):
    vendor_code: Optional[str] = Field(None, min_length=2, max_length=100)
    supplier_code: Optional[str] = Field(None, min_length=2, max_length=100, description="Alias for vendor_code")
    vendor_name: Optional[str] = Field(None, min_length=2, max_length=255)
    supplier_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Alias for vendor_name")
    name: Optional[str] = Field(None, min_length=2, max_length=255, description="Frontend alias for vendor_name")
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    contact_email: Optional[str] = None
    email: Optional[str] = None
    contactEmail: Optional[str] = None
    contact_phone: Optional[str] = None
    phone: Optional[str] = None
    contactPhone: Optional[str] = None
    contact_person: Optional[str] = None
    vendor_category: Optional[str] = None
    category: Optional[str] = None
    payment_terms_days: Optional[int] = Field(30, ge=0)
    default_lead_time_days: Optional[int] = Field(7, ge=1)
    lead_time_days: Optional[int] = Field(7, ge=1, description="Alias for default_lead_time_days")
    avgLeadTimeDays: Optional[int] = Field(7, ge=1, description="Frontend alias")
    rating: Optional[float] = Field(4.5, ge=0.0, le=5.0)
    on_time_delivery_rate: Optional[float] = Field(95.0, ge=0.0, le=100.0)
    quality_rating: Optional[float] = Field(4.5, ge=0.0, le=5.0)
    active_status: Optional[str] = Field("Active", max_length=50)
    status: Optional[str] = Field("Active", max_length=50, description="Alias for active_status")

    @model_validator(mode="before")
    @classmethod
    def populate_vendor_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            vc = data.get("vendor_code") or data.get("supplier_code")
            if vc:
                data["vendor_code"] = vc
                data["supplier_code"] = vc

            vn = data.get("vendor_name") or data.get("supplier_name") or data.get("name")
            if vn:
                data["vendor_name"] = vn
                data["supplier_name"] = vn
                data["name"] = vn

            em = data.get("contact_email") or data.get("email") or data.get("contactEmail")
            if em:
                data["contact_email"] = em
                data["email"] = em
                data["contactEmail"] = em

            ph = data.get("contact_phone") or data.get("phone") or data.get("contactPhone")
            if ph:
                data["contact_phone"] = ph
                data["phone"] = ph
                data["contactPhone"] = ph

            cat = data.get("vendor_category") or data.get("category")
            if cat:
                data["vendor_category"] = cat
                data["category"] = cat

            lt = data.get("default_lead_time_days") or data.get("lead_time_days") or data.get("avgLeadTimeDays")
            if lt is not None:
                data["default_lead_time_days"] = int(lt)
                data["lead_time_days"] = int(lt)
                data["avgLeadTimeDays"] = int(lt)

            st = data.get("active_status") or data.get("status")
            if st:
                data["active_status"] = st
                data["status"] = st
        return data


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    vendor_code: Optional[str] = None
    supplier_code: Optional[str] = None
    vendor_name: Optional[str] = None
    supplier_name: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    email: Optional[str] = None
    contactEmail: Optional[str] = None
    contact_phone: Optional[str] = None
    phone: Optional[str] = None
    contactPhone: Optional[str] = None
    contact_person: Optional[str] = None
    vendor_category: Optional[str] = None
    category: Optional[str] = None
    payment_terms_days: Optional[int] = None
    default_lead_time_days: Optional[int] = None
    lead_time_days: Optional[int] = None
    rating: Optional[float] = None
    on_time_delivery_rate: Optional[float] = None
    quality_rating: Optional[float] = None
    active_status: Optional[str] = None
    status: Optional[str] = None


class VendorResponse(VendorBase):
    vendor_id: int
    id: int  # frontend alias
    vendor_since: Optional[datetime] = None
    created_at: Optional[datetime] = None  # frontend alias

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# Aliases for backward compatibility
SupplierBase = VendorBase
SupplierCreate = VendorCreate
SupplierUpdate = VendorUpdate
SupplierResponse = VendorResponse


# ==========================================
# 4. Vendor / Supplier Parts Models
# ==========================================
class SupplierPartCreate(BaseModel):
    vendor_id: Optional[int] = None
    supplier_id: Optional[int] = None
    part_id: int
    unit_price: Optional[float] = Field(None, ge=0.0)
    supplier_unit_cost: Optional[float] = Field(None, ge=0.0)
    lead_time_days: int = Field(7, ge=1)
    minimum_order_quantity: int = Field(1, ge=1)

    @model_validator(mode="before")
    @classmethod
    def populate_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            vid = data.get("vendor_id") or data.get("supplier_id")
            if vid:
                data["vendor_id"] = vid
                data["supplier_id"] = vid
            cost = data.get("unit_price") if data.get("unit_price") is not None else data.get("supplier_unit_cost")
            if cost is not None:
                data["unit_price"] = cost
                data["supplier_unit_cost"] = cost
        return data


class SupplierPartResponse(BaseModel):
    id: int
    vendor_id: int
    supplier_id: int
    vendor_name: Optional[str] = None
    supplier_name: Optional[str] = None
    vendor_code: Optional[str] = None
    supplier_code: Optional[str] = None
    part_id: int
    part_name: Optional[str] = None
    part_number: Optional[str] = None
    sku: Optional[str] = None
    supplier_unit_cost: float
    vendor_unit_cost: Optional[float] = None
    lead_time_days: int
    minimum_order_quantity: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ==========================================
# 5. Purchase Order & Items Models
# Actual Neon Schema:
# purchase_orders: po_id, po_number, vendor_id, po_date,
#   expected_delivery_date, actual_delivery_date, status, payment_terms,
#   currency, total_order_value, created_by
# purchase_order_items: po_item_id, po_id, part_id, ordered_quantity,
#   unit_price, discount_percentage, tax_percentage, line_total,
#   received_quantity, pending_quantity, item_status
# ==========================================
class PurchaseOrderItemCreate(BaseModel):
    part_id: int
    ordered_quantity: Optional[int] = Field(None, gt=0)
    quantity: Optional[int] = Field(None, gt=0, description="Frontend alias for ordered_quantity")
    unit_price: Optional[float] = Field(None, ge=0.0)
    unit_cost: Optional[float] = Field(None, ge=0.0, description="Frontend alias for unit_price")
    discount_percentage: Optional[float] = Field(0.0, ge=0.0)
    tax_percentage: Optional[float] = Field(0.0, ge=0.0)
    line_total: Optional[float] = Field(None, ge=0.0)

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            qty = data.get("ordered_quantity") or data.get("quantity")
            if qty is not None:
                data["ordered_quantity"] = int(qty)
                data["quantity"] = int(qty)
            price = data.get("unit_price") if data.get("unit_price") is not None else data.get("unit_cost")
            if price is not None:
                data["unit_price"] = float(price)
                data["unit_cost"] = float(price)
        return data


class PurchaseOrderItemResponse(BaseModel):
    po_item_id: int
    id: int  # frontend alias for po_item_id
    po_id: int
    purchase_order_id: int  # frontend alias for po_id
    part_id: int
    part_name: Optional[str] = None
    part: Optional[str] = None  # frontend alias
    part_number: Optional[str] = None
    sku: Optional[str] = None  # frontend alias
    ordered_quantity: int
    quantity: int  # frontend alias
    unit_price: float
    unit_cost: float  # frontend alias
    unitPrice: Optional[float] = None  # frontend alias
    discount_percentage: Optional[float] = 0.0
    tax_percentage: Optional[float] = 0.0
    line_total: float
    total_cost: float  # frontend alias
    received_quantity: int = 0
    receivedQuantity: Optional[int] = None  # frontend alias
    pending_quantity: int = 0
    item_status: Optional[str] = "Pending"

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PurchaseOrderCreate(BaseModel):
    po_number: Optional[str] = Field(None, description="Optional custom PO Number (auto-generated if omitted)")
    vendor_id: Optional[int] = None
    supplier_id: Optional[int] = None  # alias
    vendor: Optional[str] = None  # name or code
    supplier: Optional[str] = None  # alias
    po_date: Optional[datetime] = None
    order_date: Optional[datetime] = None  # alias
    expected_delivery_date: Optional[datetime] = None
    expected_date: Optional[datetime] = None  # alias
    payment_terms: Optional[str] = None
    currency: Optional[str] = "INR"
    created_by: Optional[str] = "Procurement Officer"
    items: List[PurchaseOrderItemCreate] = Field(default_factory=list)

    # Legacy single-item shortcut
    part_id: Optional[int] = None
    quantity: Optional[int] = None
    ordered_quantity: Optional[int] = None
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None


class PurchaseOrderUpdate(BaseModel):
    vendor_id: Optional[int] = None
    supplier_id: Optional[int] = None
    expected_delivery_date: Optional[datetime] = None
    expected_date: Optional[datetime] = None
    status: Optional[str] = None
    payment_terms: Optional[str] = None
    currency: Optional[str] = None


class PurchaseOrderStatusUpdate(BaseModel):
    status: Literal["Draft", "draft", "Ordered", "ordered", "Received", "received", "Cancelled", "cancelled"]


class PurchaseOrderResponse(BaseModel):
    po_id: int
    id: int  # frontend alias
    po_number: str
    poNumber: str  # frontend alias
    vendor_id: Optional[int] = None
    supplier_id: Optional[int] = None  # frontend alias
    vendor_name: Optional[str] = None
    supplier_name: Optional[str] = None  # frontend alias
    supplier: Optional[str] = None  # frontend alias
    depot: str = "KSRTC Central Stores"
    status: str
    po_date: Optional[datetime] = None
    order_date: Optional[datetime] = None  # frontend alias
    poDate: Optional[str] = None  # frontend alias (YYYY-MM-DD)
    expected_delivery_date: Optional[datetime] = None
    expected_date: Optional[datetime] = None  # frontend alias
    expectedDelivery: Optional[str] = None  # frontend alias (YYYY-MM-DD)
    actual_delivery_date: Optional[datetime] = None
    received_date: Optional[datetime] = None  # frontend alias
    payment_terms: Optional[str] = None
    currency: Optional[str] = "INR"
    total_order_value: float
    total_value: float  # frontend alias
    total: float  # frontend alias
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None  # frontend alias
    items: List[PurchaseOrderItemResponse] = Field(default_factory=list)
    lines: List[PurchaseOrderItemResponse] = Field(default_factory=list)  # frontend alias

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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
    part_number: Optional[str] = None
    sku: Optional[str] = None
    transaction_type: str
    quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    transaction_date: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ==========================================
# 7. Demand History Models
# ==========================================
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
    part_number: Optional[str] = None
    sku: Optional[str] = None
    forecast_date: date
    forecast_quantity: float
    model_name: str
    model_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ==========================================
# 11. Optimization & AI Analytics Input Models
# ==========================================
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


# ==========================================
# 12. Health Response
# ==========================================
class HealthResponse(BaseModel):
    status: str = "ok"
    database: str = "connected"
    depot: str = "KSRTC Central Stores"
    timestamp: datetime
