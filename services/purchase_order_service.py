"""
Purchase Order Service handling multi-item PO creation, status transitions, and atomic inventory stock updates.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from psycopg import errors

from database.connection import get_db_connection
from schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderItemResponse,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdate,
    PurchaseOrderUpdate,
)

logger = logging.getLogger("ksrtc_backend.services.purchase_order")
DEPOT_NAME = "KSRTC Central Stores"


def build_po_response(po_row: dict, items: list) -> PurchaseOrderResponse:
    item_responses = []
    total_calc = 0.0
    for it in items:
        qty = it.get("ordered_quantity") if it.get("ordered_quantity") is not None else it.get("quantity", 0)
        uprice = float(it.get("unit_price") if it.get("unit_price") is not None else it.get("unit_cost", 0.0))
        disc = float(it.get("discount_percentage") or 0.0)
        tax = float(it.get("tax_percentage") or 0.0)
        ltot = float(it.get("line_total") or (qty * uprice * (1.0 - disc / 100.0) * (1.0 + tax / 100.0)))
        total_calc += ltot

        poid = it.get("po_id") or it.get("purchase_order_id")
        poi_id = it.get("po_item_id") or it.get("id")
        rec_qty = it.get("received_quantity", 0)
        pend_qty = it.get("pending_quantity", max(0, qty - rec_qty))

        item_responses.append(
            PurchaseOrderItemResponse(
                po_item_id=poi_id,
                id=poi_id,
                po_id=poid,
                purchase_order_id=poid,
                part_id=it["part_id"],
                part_name=it.get("part_name"),
                part=it.get("part_name"),
                part_number=it.get("part_number") or it.get("sku"),
                sku=it.get("part_number") or it.get("sku"),
                ordered_quantity=qty,
                quantity=qty,
                unit_price=uprice,
                unit_cost=uprice,
                unitPrice=uprice,
                discount_percentage=disc,
                tax_percentage=tax,
                line_total=ltot,
                total_cost=ltot,
                received_quantity=rec_qty,
                receivedQuantity=rec_qty,
                pending_quantity=pend_qty,
                item_status=it.get("item_status", "Pending"),
            )
        )

    tot_val = float(po_row.get("total_order_value") or po_row.get("total_value") or total_calc)
    order_dt = po_row.get("po_date") or po_row.get("order_date")
    exp_dt = po_row.get("expected_delivery_date") or po_row.get("expected_date")
    act_dt = po_row.get("actual_delivery_date") or po_row.get("received_date")

    poid = po_row.get("po_id") or po_row.get("id")
    v_id = po_row.get("vendor_id") or po_row.get("supplier_id")
    v_name = po_row.get("vendor_name") or po_row.get("supplier_name") or "Primary Vendor"

    return PurchaseOrderResponse(
        po_id=poid,
        id=poid,
        po_number=po_row["po_number"],
        poNumber=po_row["po_number"],
        vendor_id=v_id,
        supplier_id=v_id,
        vendor_name=v_name,
        supplier_name=v_name,
        supplier=v_name,
        depot=DEPOT_NAME,
        status=po_row.get("status", "Draft"),
        po_date=order_dt,
        order_date=order_dt,
        poDate=order_dt.strftime("%Y-%m-%d") if order_dt else None,
        expected_delivery_date=exp_dt,
        expected_date=exp_dt,
        expectedDelivery=exp_dt.strftime("%Y-%m-%d") if exp_dt else None,
        actual_delivery_date=act_dt,
        received_date=act_dt,
        payment_terms=po_row.get("payment_terms"),
        currency=po_row.get("currency") or "INR",
        total_order_value=tot_val,
        total_value=tot_val,
        total=tot_val,
        created_by=po_row.get("created_by") or "Procurement Officer",
        created_at=order_dt,
        items=item_responses,
        lines=item_responses,
    )


class PurchaseOrderService:
    @staticmethod
    def get_purchase_orders(status: Optional[str] = None) -> List[PurchaseOrderResponse]:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    po.po_id, po.po_id AS id, po.po_number, po.vendor_id, po.vendor_id AS supplier_id,
                    po.po_date, po.po_date AS order_date, po.expected_delivery_date, po.expected_delivery_date AS expected_date,
                    po.actual_delivery_date, po.actual_delivery_date AS received_date, po.status, po.payment_terms,
                    po.currency, po.total_order_value, po.total_order_value AS total_value, po.created_by,
                    v.vendor_name, v.vendor_name AS supplier_name
                FROM purchase_orders po
                LEFT JOIN vendors v ON v.vendor_id = po.vendor_id
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND LOWER(po.status) = LOWER(%s)"
                params.append(status)
            query += " ORDER BY po.po_id DESC"

            orders = conn.execute(query, params).fetchall()
            if not orders:
                return []

            po_ids = [o["po_id"] for o in orders]
            items_query = """
                SELECT 
                    poi.po_item_id, poi.po_item_id AS id, poi.po_id, poi.po_id AS purchase_order_id,
                    poi.part_id, poi.ordered_quantity, poi.ordered_quantity AS quantity, poi.unit_price,
                    poi.unit_price AS unit_cost, poi.discount_percentage, poi.tax_percentage, poi.line_total,
                    poi.line_total AS total_cost, poi.received_quantity, poi.pending_quantity, poi.item_status,
                    p.part_name, p.part_name AS name, p.part_number, p.part_number AS sku
                FROM purchase_order_items poi
                JOIN parts p ON p.part_id = poi.part_id
                WHERE poi.po_id = ANY(%s)
                ORDER BY poi.po_item_id ASC
            """
            all_items = conn.execute(items_query, (po_ids,)).fetchall()
            items_map: dict[int, list] = {oid: [] for oid in po_ids}
            for it in all_items:
                items_map[it["po_id"]].append(dict(it))

            return [build_po_response(dict(o), items_map[o["po_id"]]) for o in orders]

    @staticmethod
    def get_purchase_order(id_or_number: str) -> PurchaseOrderResponse:
        with get_db_connection() as conn:
            if id_or_number.isdigit():
                po = conn.execute(
                    "SELECT po.*, v.vendor_name FROM purchase_orders po LEFT JOIN vendors v ON v.vendor_id = po.vendor_id WHERE po.po_id = %s",
                    (int(id_or_number),),
                ).fetchone()
            else:
                po = conn.execute(
                    "SELECT po.*, v.vendor_name FROM purchase_orders po LEFT JOIN vendors v ON v.vendor_id = po.vendor_id WHERE po.po_number = %s",
                    (id_or_number,),
                ).fetchone()

            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found.")

            items = conn.execute(
                """SELECT poi.*, p.part_name, p.part_number, p.part_number AS sku
                   FROM purchase_order_items poi
                   JOIN parts p ON p.part_id = poi.part_id
                   WHERE poi.po_id = %s
                   ORDER BY poi.po_item_id ASC""",
                (po["po_id"],),
            ).fetchall()

            return build_po_response(dict(po), [dict(it) for it in items])

    @staticmethod
    def create_purchase_order(payload: PurchaseOrderCreate) -> PurchaseOrderResponse:
        with get_db_connection() as conn:
            with conn.transaction():
                vendor_id = payload.vendor_id or payload.supplier_id
                v_name_input = payload.vendor or payload.supplier
                if not vendor_id and v_name_input:
                    v_row = conn.execute(
                        "SELECT vendor_id FROM vendors WHERE LOWER(vendor_name) = LOWER(%s) OR LOWER(vendor_code) = LOWER(%s) LIMIT 1",
                        (v_name_input.strip(), v_name_input.strip()),
                    ).fetchone()
                    if v_row:
                        vendor_id = v_row["vendor_id"]

                po_num = payload.po_number
                if not po_num:
                    year = datetime.now().year
                    seq_row = conn.execute("SELECT COUNT(*) + 1 AS count FROM purchase_orders").fetchone()
                    seq = seq_row["count"] if seq_row else 1
                    po_num = f"PO-{year}-{seq:04d}"

                items_to_create = list(payload.items)
                single_qty = payload.ordered_quantity or payload.quantity
                if not items_to_create and payload.part_id and single_qty:
                    unit_c = payload.unit_price if payload.unit_price is not None else payload.unit_cost
                    if unit_c is None:
                        p_cost = conn.execute("SELECT standard_cost FROM parts WHERE part_id = %s", (payload.part_id,)).fetchone()
                        unit_c = float(p_cost["standard_cost"]) if p_cost else 0.0
                    items_to_create.append(PurchaseOrderItemCreate(part_id=payload.part_id, ordered_quantity=single_qty, unit_price=unit_c))

                if not items_to_create:
                    raise HTTPException(status_code=400, detail="Purchase order must contain at least one line item.")

                total_val = 0.0
                processed_items = []
                for it in items_to_create:
                    qty = it.ordered_quantity or it.quantity or 1
                    u_price = it.unit_price if it.unit_price is not None else (it.unit_cost or 0.0)
                    disc = it.discount_percentage or 0.0
                    tax = it.tax_percentage or 0.0
                    ltot = it.line_total if it.line_total is not None else round(qty * u_price * (1.0 - disc / 100.0) * (1.0 + tax / 100.0), 2)
                    total_val += ltot
                    processed_items.append({
                        "part_id": it.part_id,
                        "ordered_quantity": qty,
                        "unit_price": u_price,
                        "discount_percentage": disc,
                        "tax_percentage": tax,
                        "line_total": ltot,
                    })

                order_dt = payload.po_date or payload.order_date or datetime.now(timezone.utc)
                exp_dt = payload.expected_delivery_date or payload.expected_date

                po_record = conn.execute(
                    """INSERT INTO purchase_orders 
                       (po_number, vendor_id, po_date, expected_delivery_date, status, payment_terms, currency, total_order_value, created_by)
                       VALUES (%s, %s, %s, %s, 'Draft', %s, %s, %s, %s)
                       RETURNING *""",
                    (po_num, vendor_id, order_dt, exp_dt, payload.payment_terms or "Net 30", payload.currency or "INR", total_val, payload.created_by or "Procurement Officer"),
                ).fetchone()

                created_items = []
                for it in processed_items:
                    part = conn.execute("SELECT part_id, part_name, part_number FROM parts WHERE part_id = %s", (it["part_id"],)).fetchone()
                    if not part:
                        raise HTTPException(status_code=404, detail=f"Part with id {it['part_id']} not found.")

                    item_row = conn.execute(
                        """INSERT INTO purchase_order_items 
                           (po_id, part_id, ordered_quantity, unit_price, discount_percentage, tax_percentage, line_total, received_quantity, pending_quantity, item_status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, 'Pending')
                           RETURNING *""",
                        (po_record["po_id"], it["part_id"], it["ordered_quantity"], it["unit_price"], it["discount_percentage"], it["tax_percentage"], it["line_total"], it["ordered_quantity"]),
                    ).fetchone()

                    item_dict = dict(item_row)
                    item_dict["part_name"] = part["part_name"]
                    item_dict["part_number"] = part["part_number"]
                    item_dict["sku"] = part["part_number"]
                    created_items.append(item_dict)

                    conn.execute(
                        """UPDATE inventory 
                           SET stock_in_transit = COALESCE(stock_in_transit, 0) + %s,
                               last_updated = NOW()
                           WHERE part_id = %s""",
                        (it["ordered_quantity"], it["part_id"]),
                    )

                v_name = None
                if vendor_id:
                    v_row = conn.execute("SELECT vendor_name FROM vendors WHERE vendor_id = %s", (vendor_id,)).fetchone()
                    if v_row:
                        v_name = v_row["vendor_name"]

                po_dict = dict(po_record)
                po_dict["vendor_name"] = v_name
                return build_po_response(po_dict, created_items)

    @staticmethod
    def update_purchase_order_status(id_or_number: str, payload: PurchaseOrderStatusUpdate) -> PurchaseOrderResponse:
        target_status = payload.status.capitalize()
        with get_db_connection() as conn:
            with conn.transaction():
                where_clause = "po_id = %s" if id_or_number.isdigit() else "po_number = %s"
                val = int(id_or_number) if id_or_number.isdigit() else id_or_number

                po = conn.execute(f"SELECT * FROM purchase_orders WHERE {where_clause} FOR UPDATE", (val,)).fetchone()
                if not po:
                    raise HTTPException(status_code=404, detail="Purchase order not found.")

                curr_status = po["status"].capitalize()
                if curr_status == target_status:
                    return PurchaseOrderService.get_purchase_order(str(po["po_id"]))

                if curr_status in ("Received", "Cancelled") and target_status in ("Received", "Draft"):
                    raise HTTPException(status_code=409, detail=f"Cannot change status of an already '{curr_status}' purchase order.")

                if target_status == "Received":
                    items = conn.execute("SELECT * FROM purchase_order_items WHERE po_id = %s FOR UPDATE", (po["po_id"],)).fetchall()
                    for item in items:
                        part_id = item["part_id"]
                        qty_ordered = item["ordered_quantity"]
                        qty_already_received = item.get("received_quantity", 0) or 0
                        qty_to_add = max(0, qty_ordered - qty_already_received)

                        if qty_to_add > 0:
                            conn.execute(
                                """INSERT INTO inventory 
                                   (part_id, current_stock, reserved_stock, available_stock, stock_in_transit, 
                                    reorder_point, safety_stock, maximum_stock, last_receipt_date, last_updated)
                                   VALUES (%s, %s, 0, %s, 0, 10, 5, 50, NOW(), NOW())
                                   ON CONFLICT (part_id) DO UPDATE
                                   SET current_stock = inventory.current_stock + EXCLUDED.current_stock,
                                       available_stock = inventory.available_stock + EXCLUDED.current_stock,
                                       stock_in_transit = GREATEST(0, COALESCE(inventory.stock_in_transit, 0) - EXCLUDED.current_stock),
                                       last_receipt_date = NOW(),
                                       last_updated = NOW()""",
                                (part_id, qty_to_add, qty_to_add),
                            )

                            try:
                                conn.execute(
                                    """INSERT INTO inventory_transactions 
                                       (part_id, transaction_type, quantity, reference_type, reference_id, transaction_date, notes)
                                       VALUES (%s, 'PO_RECEIPT', %s, 'PURCHASE_ORDER', %s, NOW(), %s)""",
                                    (part_id, qty_to_add, po["po_number"], f"Receipt of {qty_to_add} units from Purchase Order {po['po_number']}"),
                                )
                            except Exception as tx_err:
                                logger.debug(f"Inventory transaction notice: {tx_err}")

                            conn.execute(
                                """UPDATE purchase_order_items 
                                   SET received_quantity = ordered_quantity, 
                                       pending_quantity = 0, 
                                       item_status = 'Received' 
                                   WHERE po_item_id = %s""",
                                (item["po_item_id"],),
                            )

                    conn.execute("UPDATE purchase_orders SET status = 'Received', actual_delivery_date = NOW() WHERE po_id = %s", (po["po_id"],))
                else:
                    conn.execute("UPDATE purchase_orders SET status = %s WHERE po_id = %s", (target_status, po["po_id"]))

                return PurchaseOrderService.get_purchase_order(str(po["po_id"]))
