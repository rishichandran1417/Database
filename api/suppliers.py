"""
Suppliers & Vendors API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import errors

from utils.validation import verify_api_key
from schemas.supplier import (
    SupplierCreate,
    SupplierPartCreate,
    SupplierPartResponse,
    SupplierResponse,
    SupplierUpdate,
    VendorCreate,
    VendorResponse,
    VendorUpdate,
)
from database.connection import get_db_connection

router = APIRouter(tags=["Vendors & Suppliers"])


def build_vendor_dict(r: dict) -> dict:
    item = dict(r)
    vid = item["vendor_id"]
    vcode = item["vendor_code"]
    vname = item["vendor_name"]
    email = item.get("contact_email")
    phone = item.get("contact_phone")
    cat = item.get("vendor_category")
    lead_time = item.get("default_lead_time_days", 7)
    stat = item.get("active_status", "Active")
    since = item.get("vendor_since")

    item["id"] = vid
    item["supplier_code"] = vcode
    item["supplier_name"] = vname
    item["name"] = vname
    item["email"] = email
    item["contactEmail"] = email
    item["phone"] = phone
    item["contactPhone"] = phone
    item["category"] = cat
    item["lead_time_days"] = lead_time
    item["avgLeadTimeDays"] = lead_time
    item["status"] = stat
    item["created_at"] = since
    return item


@router.get("/vendors", response_model=List[VendorResponse])
@router.get("/suppliers", response_model=List[SupplierResponse])
def get_vendors(status: Optional[str] = None, category: Optional[str] = None):
    query = "SELECT * FROM vendors WHERE 1=1"
    params = []
    if status:
        query += " AND LOWER(active_status) = LOWER(%s)"
        params.append(status)
    if category:
        query += " AND LOWER(vendor_category) = LOWER(%s)"
        params.append(category)
    query += " ORDER BY vendor_name ASC"

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [build_vendor_dict(dict(r)) for r in rows]


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
@router.get("/suppliers/{vendor_id}", response_model=SupplierResponse)
def get_vendor_by_id(vendor_id: int):
    with get_db_connection() as conn:
        vendor = conn.execute("SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id,)).fetchone()
        if not vendor:
            raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found.")
        return build_vendor_dict(dict(vendor))


@router.post("/vendors", response_model=VendorResponse, status_code=201, dependencies=[Depends(verify_api_key)])
@router.post("/suppliers", response_model=SupplierResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_vendor(payload: VendorCreate):
    vcode = payload.vendor_code or payload.supplier_code
    vname = payload.vendor_name or payload.supplier_name or payload.name
    email = payload.contact_email or payload.email or payload.contactEmail
    phone = payload.contact_phone or payload.phone or payload.contactPhone
    cat = payload.vendor_category or payload.category
    lead_time = payload.default_lead_time_days or payload.lead_time_days or payload.avgLeadTimeDays or 7
    stat = payload.active_status or payload.status or "Active"

    try:
        with get_db_connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """INSERT INTO vendors 
                       (vendor_code, vendor_name, city, state, country, 
                        contact_email, contact_phone, vendor_category, 
                        payment_terms_days, default_lead_time_days, rating, 
                        on_time_delivery_rate, quality_rating, active_status, vendor_since)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       RETURNING *""",
                    (
                        vcode.strip(),
                        vname.strip(),
                        payload.city,
                        payload.state,
                        payload.country or "India",
                        email,
                        phone,
                        cat,
                        payload.payment_terms_days or 30,
                        lead_time,
                        payload.rating or 4.5,
                        payload.on_time_delivery_rate or 95.0,
                        payload.quality_rating or 4.5,
                        stat,
                    ),
                ).fetchone()
                return build_vendor_dict(dict(row))
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"Vendor code '{vcode}' already exists.")


@router.put("/vendors/{vendor_id}", response_model=VendorResponse, dependencies=[Depends(verify_api_key)])
@router.put("/suppliers/{vendor_id}", response_model=SupplierResponse, dependencies=[Depends(verify_api_key)])
def update_vendor(vendor_id: int, payload: VendorUpdate):
    with get_db_connection() as conn:
        with conn.transaction():
            existing = conn.execute("SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id,)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found.")

            update_data = payload.model_dump(exclude_unset=True)
            if not update_data:
                return build_vendor_dict(dict(existing))

            db_update = {}
            for k, v in update_data.items():
                if k in ("supplier_code",):
                    db_update["vendor_code"] = v
                elif k in ("supplier_name", "name"):
                    db_update["vendor_name"] = v
                elif k in ("email", "contactEmail"):
                    db_update["contact_email"] = v
                elif k in ("phone", "contactPhone"):
                    db_update["contact_phone"] = v
                elif k in ("category",):
                    db_update["vendor_category"] = v
                elif k in ("lead_time_days", "avgLeadTimeDays"):
                    db_update["default_lead_time_days"] = v
                elif k in ("status",):
                    db_update["active_status"] = v
                else:
                    db_update[k] = v

            if db_update:
                set_clauses = [f"{k} = %s" for k in db_update.keys()]
                values = list(db_update.values())
                values.append(vendor_id)
                try:
                    query = f"UPDATE vendors SET {', '.join(set_clauses)} WHERE vendor_id = %s RETURNING *"
                    updated = conn.execute(query, values).fetchone()
                    return build_vendor_dict(dict(updated))
                except errors.UniqueViolation:
                    raise HTTPException(status_code=409, detail="Vendor code already in use.")
            return build_vendor_dict(dict(existing))


@router.delete("/vendors/{vendor_id}", status_code=204, dependencies=[Depends(verify_api_key)])
@router.delete("/suppliers/{vendor_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_vendor(vendor_id: int):
    with get_db_connection() as conn:
        with conn.transaction():
            deleted = conn.execute("DELETE FROM vendors WHERE vendor_id = %s RETURNING vendor_id", (vendor_id,)).fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found.")
    return None


@router.get("/vendor-parts", response_model=List[SupplierPartResponse])
@router.get("/supplier-parts", response_model=List[SupplierPartResponse])
def get_supplier_parts(supplier_id: Optional[int] = None, vendor_id: Optional[int] = None, part_id: Optional[int] = None):
    target_vid = vendor_id or supplier_id
    with get_db_connection() as conn:
        query = """
            SELECT DISTINCT ON (poi.part_id, po.vendor_id)
                poi.po_item_id AS id,
                po.vendor_id,
                po.vendor_id AS supplier_id,
                v.vendor_name,
                v.vendor_name AS supplier_name,
                v.vendor_code,
                v.vendor_code AS supplier_code,
                poi.part_id,
                p.part_name,
                p.part_number,
                p.part_number AS sku,
                poi.unit_price AS supplier_unit_cost,
                poi.unit_price AS vendor_unit_cost,
                COALESCE(p.lead_time_days, v.default_lead_time_days, 7) AS lead_time_days,
                COALESCE(p.minimum_order_quantity, 1) AS minimum_order_quantity
            FROM purchase_order_items poi
            JOIN purchase_orders po ON po.po_id = poi.po_id
            JOIN vendors v ON v.vendor_id = po.vendor_id
            JOIN parts p ON p.part_id = poi.part_id
            WHERE 1=1
        """
        params = []
        if target_vid:
            query += " AND po.vendor_id = %s"
            params.append(target_vid)
        if part_id:
            query += " AND poi.part_id = %s"
            params.append(part_id)
        query += " ORDER BY poi.part_id, po.vendor_id, po.po_date DESC NULLS LAST"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@router.post("/vendor-parts", response_model=SupplierPartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
@router.post("/supplier-parts", response_model=SupplierPartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_or_update_supplier_part(payload: SupplierPartCreate):
    vid = payload.vendor_id or payload.supplier_id
    cost = payload.unit_price if payload.unit_price is not None else payload.supplier_unit_cost
    with get_db_connection() as conn:
        p = conn.execute("SELECT part_id, part_name, part_number FROM parts WHERE part_id = %s", (payload.part_id,)).fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Part not found.")
        v = conn.execute("SELECT vendor_id, vendor_name, vendor_code, default_lead_time_days FROM vendors WHERE vendor_id = %s", (vid,)).fetchone()
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found.")

        return SupplierPartResponse(
            id=payload.part_id,
            vendor_id=vid,
            supplier_id=vid,
            vendor_name=v["vendor_name"],
            supplier_name=v["vendor_name"],
            vendor_code=v["vendor_code"],
            supplier_code=v["vendor_code"],
            part_id=payload.part_id,
            part_name=p["part_name"],
            part_number=p["part_number"],
            sku=p["part_number"],
            supplier_unit_cost=float(cost or 0.0),
            vendor_unit_cost=float(cost or 0.0),
            lead_time_days=payload.lead_time_days or v["default_lead_time_days"] or 7,
            minimum_order_quantity=payload.minimum_order_quantity or 1,
        )
