"""
Inventory Service handling parts catalog, stock level calculations, and inventory transactions.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from psycopg import errors

from database.connection import get_db_connection
from database.queries import (
    SELECT_ALL_PARTS,
    SELECT_PART_BY_ID,
    INSERT_PART,
    DELETE_PART,
    SELECT_ALL_INVENTORY,
    SELECT_INVENTORY_BY_PART_ID,
    UPSERT_INVENTORY,
)
from schemas.inventory import (
    PartCreate,
    PartUpdate,
    PartResponse,
    InventoryUpdate,
    InventoryItemResponse,
    InventoryTransactionCreate,
    InventoryTransactionResponse,
)

logger = logging.getLogger("ksrtc_backend.services.inventory")
DEPOT_NAME = "KSRTC Central Stores"


def build_part_dict(r: dict) -> dict:
    item = dict(r)
    pid = item["part_id"]
    pnum = item["part_number"]
    pname = item["part_name"]
    cost = float(item["standard_cost"]) if item.get("standard_cost") is not None else 0.0
    cdate = item.get("created_date")

    item["id"] = pid
    item["sku"] = pnum
    item["name"] = pname
    item["unit_cost"] = cost
    item["created_at"] = cdate
    return item


def build_inventory_dict(r: dict) -> dict:
    item = dict(r)
    qty = item.get("current_stock") if item.get("current_stock") is not None else 0
    safety = item.get("safety_stock") if item.get("safety_stock") is not None else 5
    reorder = item.get("reorder_point") if item.get("reorder_point") is not None else 10

    if qty <= safety:
        st = "Critical"
        risk = "High"
    elif qty <= reorder:
        st = "Warning"
        risk = "Medium"
    else:
        st = "Healthy"
        risk = "Low"

    item["status"] = st
    item["stockoutRisk"] = risk
    item["depot"] = DEPOT_NAME
    item["daysOfSupply"] = max(1, round(qty / 3)) if qty > 0 else 0
    return item


class InventoryService:
    @staticmethod
    def get_parts(category: Optional[str] = None, criticality: Optional[str] = None, search: Optional[str] = None) -> List[dict]:
        query = SELECT_ALL_PARTS
        params = []
        if category:
            query += " AND LOWER(category) = LOWER(%s)"
            params.append(category)
        if criticality:
            query += " AND LOWER(criticality) = LOWER(%s)"
            params.append(criticality)
        if search:
            query += " AND (LOWER(part_name) LIKE LOWER(%s) OR LOWER(part_number) LIKE LOWER(%s))"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY part_name ASC"

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [build_part_dict(dict(r)) for r in rows]

    @staticmethod
    def get_part_by_id(part_id: int) -> dict:
        with get_db_connection() as conn:
            part = conn.execute(SELECT_PART_BY_ID, (part_id,)).fetchone()
            if not part:
                raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")
            return build_part_dict(dict(part))

    @staticmethod
    def create_part(payload: PartCreate) -> dict:
        pnum = payload.part_number or payload.sku
        pname = payload.part_name or payload.name
        cost = payload.standard_cost if payload.standard_cost is not None else (payload.unit_cost or 0.0)

        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    part = conn.execute(
                        INSERT_PART,
                        (
                            pnum.strip(),
                            pname.strip(),
                            payload.category.strip(),
                            payload.sub_category,
                            payload.description,
                            payload.unit_of_measure or "Each",
                            payload.criticality or "Essential",
                            payload.vehicle_system,
                            cost,
                            payload.minimum_order_quantity or 1,
                            payload.reorder_point or 10,
                            payload.safety_stock or 5,
                            payload.lead_time_days or 7,
                            payload.annual_demand or 0.0,
                            payload.active_status or "Active",
                        ),
                    ).fetchone()

                    # Initialize inventory record
                    conn.execute(
                        """INSERT INTO inventory 
                           (part_id, current_stock, reserved_stock, available_stock, stock_in_transit, 
                            reorder_point, safety_stock, maximum_stock, average_unit_cost, inventory_value, last_updated)
                           VALUES (%s, 0, 0, 0, 0, %s, %s, 50, %s, 0.0, NOW())
                           ON CONFLICT (part_id) DO NOTHING""",
                        (part["part_id"], payload.reorder_point or 10, payload.safety_stock or 5, cost),
                    )
                    return build_part_dict(dict(part))
        except errors.UniqueViolation:
            raise HTTPException(status_code=409, detail=f"A part with part_number '{pnum}' already exists.")

    @staticmethod
    def update_part(part_id: int, payload: PartUpdate) -> dict:
        with get_db_connection() as conn:
            existing = conn.execute(SELECT_PART_BY_ID, (part_id,)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")

            update_data = payload.model_dump(exclude_unset=True)
            if not update_data:
                return build_part_dict(dict(existing))

            db_update = {}
            for k, v in update_data.items():
                if k == "sku":
                    db_update["part_number"] = v
                elif k == "name":
                    db_update["part_name"] = v
                elif k == "unit_cost":
                    db_update["standard_cost"] = v
                else:
                    db_update[k] = v

            set_clauses = [f"{k} = %s" for k in db_update.keys()]
            values = list(db_update.values())
            values.append(part_id)

            query = f"UPDATE parts SET {', '.join(set_clauses)} WHERE part_id = %s RETURNING *"
            try:
                updated = conn.execute(query, values).fetchone()
                conn.commit()
                return build_part_dict(dict(updated))
            except errors.UniqueViolation:
                raise HTTPException(status_code=409, detail="Part number already exists on another part.")

    @staticmethod
    def delete_part(part_id: int) -> None:
        with get_db_connection() as conn:
            with conn.transaction():
                deleted = conn.execute(DELETE_PART, (part_id,)).fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")

    @staticmethod
    def get_inventory() -> List[dict]:
        with get_db_connection() as conn:
            rows = conn.execute(SELECT_ALL_INVENTORY).fetchall()
            return [build_inventory_dict(dict(r)) for r in rows]

    @staticmethod
    def get_inventory_for_part(part_id: int) -> dict:
        with get_db_connection() as conn:
            row = conn.execute(SELECT_INVENTORY_BY_PART_ID, (part_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Inventory for part id {part_id} not found.")
            return build_inventory_dict(dict(row))

    @staticmethod
    def update_inventory(part_id: int, payload: InventoryUpdate) -> dict:
        with get_db_connection() as conn:
            with conn.transaction():
                part = conn.execute(SELECT_PART_BY_ID, (part_id,)).fetchone()
                if not part:
                    raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")

                existing = conn.execute("SELECT * FROM inventory WHERE part_id = %s", (part_id,)).fetchone()
                old_qty = existing["current_stock"] if existing else 0

                cur_qty = payload.current_stock if payload.current_stock is not None else (existing["current_stock"] if existing else 0)
                reorder = payload.reorder_point if payload.reorder_point is not None else (existing["reorder_point"] if existing else (part["reorder_point"] or 10))
                safety = payload.safety_stock if payload.safety_stock is not None else (existing["safety_stock"] if existing else (part["safety_stock"] or 5))
                max_stk = payload.maximum_stock if payload.maximum_stock is not None else (existing["maximum_stock"] if existing else 50)
                res_stk = payload.reserved_stock if payload.reserved_stock is not None else (existing["reserved_stock"] if existing else 0)
                in_transit = payload.stock_in_transit if payload.stock_in_transit is not None else (existing["stock_in_transit"] if existing else 0)
                avg_cost = payload.average_unit_cost if payload.average_unit_cost is not None else (existing["average_unit_cost"] if existing else float(part["standard_cost"] or 0))
                avail_stk = max(0, cur_qty - res_stk)
                inv_val = round(cur_qty * avg_cost, 2)

                conn.execute(
                    UPSERT_INVENTORY,
                    (part_id, cur_qty, res_stk, avail_stk, in_transit, reorder, safety, max_stk, avg_cost, inv_val),
                )

                qty_diff = cur_qty - old_qty
                if qty_diff != 0:
                    try:
                        conn.execute(
                            """INSERT INTO inventory_transactions 
                               (part_id, transaction_type, quantity, reference_type, reference_id, notes)
                               VALUES (%s, 'ADJUSTMENT', %s, 'MANUAL_AUDIT', 'STOCK_UPDATE', 'Manual stock level adjustment')""",
                            (part_id, qty_diff),
                        )
                    except Exception as tx_err:
                        logger.debug(f"inventory_transactions record notice: {tx_err}")

                return InventoryService.get_inventory_for_part(part_id)
