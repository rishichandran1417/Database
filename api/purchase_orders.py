"""
Purchase Orders API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from utils.validation import verify_api_key
from services.purchase_order_service import PurchaseOrderService
from schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdate,
    PurchaseOrderUpdate,
)
from database.connection import get_db_connection

router = APIRouter(tags=["Purchase Orders"])


@router.get("/purchase-orders", response_model=List[PurchaseOrderResponse])
def get_purchase_orders(status: Optional[str] = None):
    return PurchaseOrderService.get_purchase_orders(status)


@router.get("/purchase-orders/{id_or_number}", response_model=PurchaseOrderResponse)
def get_purchase_order(id_or_number: str):
    return PurchaseOrderService.get_purchase_order(id_or_number)


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_purchase_order(payload: PurchaseOrderCreate):
    return PurchaseOrderService.create_purchase_order(payload)


@router.put("/purchase-orders/{id_or_number}", response_model=PurchaseOrderResponse, dependencies=[Depends(verify_api_key)])
def update_purchase_order(id_or_number: str, payload: PurchaseOrderUpdate):
    with get_db_connection() as conn:
        with conn.transaction():
            where_clause = "po_id = %s" if id_or_number.isdigit() else "po_number = %s"
            val = int(id_or_number) if id_or_number.isdigit() else id_or_number
            po = conn.execute(f"SELECT * FROM purchase_orders WHERE {where_clause}", (val,)).fetchone()
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found.")

            update_data = payload.model_dump(exclude_unset=True)
            db_update = {}
            for k, v in update_data.items():
                if k in ("supplier_id",):
                    db_update["vendor_id"] = v
                elif k in ("expected_date",):
                    db_update["expected_delivery_date"] = v
                else:
                    db_update[k] = v

            if db_update:
                set_clauses = [f"{k} = %s" for k in db_update.keys()]
                vals = list(db_update.values())
                vals.append(po["po_id"])
                conn.execute(f"UPDATE purchase_orders SET {', '.join(set_clauses)} WHERE po_id = %s", vals)

            return PurchaseOrderService.get_purchase_order(str(po["po_id"]))


@router.patch("/purchase-orders/{id_or_number}/status", response_model=PurchaseOrderResponse, dependencies=[Depends(verify_api_key)])
def update_purchase_order_status(id_or_number: str, payload: PurchaseOrderStatusUpdate):
    return PurchaseOrderService.update_purchase_order_status(id_or_number, payload)
