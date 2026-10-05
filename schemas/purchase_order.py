from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
