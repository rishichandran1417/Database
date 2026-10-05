from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
