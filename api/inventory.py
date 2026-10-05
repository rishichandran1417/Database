"""
Inventory and Parts Catalog API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from utils.validation import verify_api_key
from services.inventory_service import InventoryService
from schemas.inventory import (
    PartCreate,
    PartUpdate,
    PartResponse,
    InventoryUpdate,
    InventoryItemResponse,
    InventoryTransactionCreate,
    InventoryTransactionResponse,
)
from database.connection import get_db_connection

router = APIRouter(tags=["Inventory & Parts"])


# Parts catalog
@router.get("/parts", response_model=List[PartResponse])
def get_parts(category: Optional[str] = None, criticality: Optional[str] = None, search: Optional[str] = None):
    return InventoryService.get_parts(category, criticality, search)


@router.get("/parts/{part_id}", response_model=PartResponse)
def get_part_by_id(part_id: int):
    return InventoryService.get_part_by_id(part_id)


@router.post("/parts", response_model=PartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_part(payload: PartCreate):
    return InventoryService.create_part(payload)


@router.put("/parts/{part_id}", response_model=PartResponse, dependencies=[Depends(verify_api_key)])
def update_part(part_id: int, payload: PartUpdate):
    return InventoryService.update_part(part_id, payload)


@router.delete("/parts/{part_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_part(part_id: int):
    InventoryService.delete_part(part_id)
    return None


# Inventory stock
@router.get("/inventory", response_model=List[InventoryItemResponse])
@router.get("/inventory/inventory", response_model=List[InventoryItemResponse], include_in_schema=False)
def get_inventory():
    return InventoryService.get_inventory()


@router.get("/inventory/{part_id}", response_model=InventoryItemResponse)
def get_inventory_for_part(part_id: int):
    return InventoryService.get_inventory_for_part(part_id)


@router.put("/inventory/{part_id}", response_model=InventoryItemResponse, dependencies=[Depends(verify_api_key)])
def update_inventory(part_id: int, payload: InventoryUpdate):
    return InventoryService.update_inventory(part_id, payload)


# Inventory transactions audit trail
@router.get("/inventory-transactions", response_model=List[InventoryTransactionResponse])
def get_inventory_transactions(
    part_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    query = """
        SELECT it.*, p.part_name, p.part_number, p.part_number AS sku
        FROM inventory_transactions it
        JOIN parts p ON p.part_id = it.part_id
        WHERE 1=1
    """
    params = []
    if part_id:
        query += " AND it.part_id = %s"
        params.append(part_id)
    if transaction_type:
        query += " AND it.transaction_type = %s"
        params.append(transaction_type)
    query += " ORDER BY it.transaction_date DESC, it.id DESC LIMIT %s"
    params.append(limit)

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@router.post("/inventory-transactions", response_model=InventoryTransactionResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_inventory_transaction(payload: InventoryTransactionCreate):
    with get_db_connection() as conn:
        with conn.transaction():
            part = conn.execute("SELECT part_id, part_name, part_number FROM parts WHERE part_id = %s", (payload.part_id,)).fetchone()
            if not part:
                raise HTTPException(status_code=404, detail="Part not found.")

            tx = conn.execute(
                """INSERT INTO inventory_transactions (part_id, transaction_type, quantity, reference_type, reference_id, notes)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
                (payload.part_id, payload.transaction_type, payload.quantity, payload.reference_type, payload.reference_id, payload.notes),
            ).fetchone()

            conn.execute(
                """INSERT INTO inventory (part_id, current_stock, available_stock, reorder_point, safety_stock, maximum_stock, last_updated)
                   VALUES (%s, GREATEST(0, %s), GREATEST(0, %s), 10, 5, 50, NOW())
                   ON CONFLICT (part_id) DO UPDATE
                   SET current_stock = GREATEST(0, inventory.current_stock + %s),
                       available_stock = GREATEST(0, inventory.available_stock + %s),
                       last_updated = NOW()""",
                (payload.part_id, payload.quantity, payload.quantity, payload.quantity, payload.quantity),
            )

            item = dict(tx)
            item["part_name"] = part["part_name"]
            item["part_number"] = part["part_number"]
            item["sku"] = part["part_number"]
            return item
