import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg import errors

from database import (
    DATABASE_URL,
    check_db_health,
    close_connection_pool,
    get_db_connection,
    init_db,
)
from models import (
    DemandHistoryBatchCreate,
    DemandHistoryCreate,
    DemandHistoryResponse,
    ForecastBatchCreate,
    ForecastCreate,
    ForecastResponse,
    HealthResponse,
    InventoryItemResponse,
    InventoryTransactionCreate,
    InventoryTransactionResponse,
    InventoryUpdate,
    ModelRunCreate,
    ModelRunResponse,
    PartCreate,
    PartResponse,
    PartUpdate,
    ProcurementRecommendationBatchCreate,
    ProcurementRecommendationCreate,
    ProcurementRecommendationResponse,
    PurchaseOrderCreate,
    PurchaseOrderItemResponse,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdate,
    PurchaseOrderUpdate,
    PuLPOptimizationInputItem,
    PuLPOptimizationInputResponse,
    SupplierCreate,
    SupplierPartCreate,
    SupplierPartResponse,
    SupplierResponse,
    SupplierUpdate,
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ksrtc_backend")

# Environment configuration
API_KEY = os.getenv("API_KEY")
ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]

DEPOT_NAME = "KSRTC Central Depot, Thiruvananthapuram"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    try:
        init_db()
    except Exception as e:
        logger.error(f"Error during database initialization: {e}", exc_info=True)
    yield
    logger.info("Application shutting down...")
    close_connection_pool()


app = FastAPI(
    title="KSRTC Central Depot Supply-Chain & Procurement API",
    description="Central backend API & database source of truth for KSRTC spare-parts procurement, inventory, demand forecasting, and PuLP optimization.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verifies X-API-Key header if API_KEY environment variable is configured."""
    if API_KEY and API_KEY.strip():
        if not x_api_key or x_api_key.strip() != API_KEY.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key authentication header.",
            )


# Router with prefix /api/v1/db
router = APIRouter(prefix="/api/v1/db")


# =====================================================================
# 1. Health Endpoints
# =====================================================================
@router.get("/health", response_model=HealthResponse)
def health_check():
    try:
        alive = check_db_health()
        if not alive:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database health query failed.",
            )
        return HealthResponse(
            status="ok",
            database="connected",
            depot=DEPOT_NAME,
            timestamp=datetime.now(timezone.utc),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: {type(e).__name__}",
        )


@app.get("/health", response_model=HealthResponse)
def root_health():
    return health_check()


@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "KSRTC Central Depot Procurement & Supply-Chain API",
        "docs_url": "/docs",
        "api_prefix": "/api/v1/db",
        "depot": DEPOT_NAME,
    }


# =====================================================================
# 2. Parts Catalog Endpoints
# =====================================================================
@router.get("/parts", response_model=List[PartResponse])
def get_parts(
    category: Optional[str] = None,
    criticality: Optional[str] = None,
    search: Optional[str] = None,
):
    try:
        query = "SELECT * FROM parts WHERE 1=1"
        params = []
        if category:
            query += " AND LOWER(category) = LOWER(%s)"
            params.append(category)
        if criticality:
            query += " AND LOWER(criticality) = LOWER(%s)"
            params.append(criticality)
        if search:
            query += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(sku) LIKE LOWER(%s))"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY name ASC"

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching parts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch parts catalog.")


@router.get("/parts/{part_id}", response_model=PartResponse)
def get_part_by_id(part_id: int):
    try:
        with get_db_connection() as conn:
            part = conn.execute("SELECT * FROM parts WHERE id = %s", (part_id,)).fetchone()
            if not part:
                raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")
            return dict(part)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch part.")


@router.post("/parts", response_model=PartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_part(payload: PartCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                part = conn.execute(
                    """INSERT INTO parts (sku, name, category, description, unit_cost, criticality)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING *""",
                    (
                        payload.sku.strip(),
                        payload.name.strip(),
                        payload.category.strip(),
                        payload.description,
                        payload.unit_cost,
                        payload.criticality,
                    ),
                ).fetchone()

                # Automatically initialize inventory record for newly created part
                conn.execute(
                    """INSERT INTO inventory (part_id, quantity, reorder_point, safety_stock, max_stock)
                       VALUES (%s, 0, 10, 5, 50)
                       ON CONFLICT (part_id) DO NOTHING""",
                    (part["id"],),
                )
                return dict(part)
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"A part with SKU '{payload.sku}' already exists.")
    except Exception as e:
        logger.error(f"Error creating part: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create part.")


@router.put("/parts/{part_id}", response_model=PartResponse, dependencies=[Depends(verify_api_key)])
def update_part(part_id: int, payload: PartUpdate):
    try:
        with get_db_connection() as conn:
            existing = conn.execute("SELECT * FROM parts WHERE id = %s", (part_id,)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")

            update_data = payload.model_dump(exclude_unset=True)
            if not update_data:
                return dict(existing)

            set_clauses = [f"{k} = %s" for k in update_data.keys()]
            values = list(update_data.values())
            values.append(part_id)

            query = f"UPDATE parts SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
            updated = conn.execute(query, values).fetchone()
            conn.commit()
            return dict(updated)
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="SKU already exists on another part.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update part.")


@router.delete("/parts/{part_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_part(part_id: int):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                deleted = conn.execute("DELETE FROM parts WHERE id = %s RETURNING id", (part_id,)).fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete part.")


# =====================================================================
# 3. Inventory Stock Endpoints
# =====================================================================
@router.get("/inventory", response_model=List[InventoryItemResponse])
@router.get("/inventory/inventory", response_model=List[InventoryItemResponse], include_in_schema=False)
def get_inventory():
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT 
                    i.id,
                    p.id AS part_id,
                    p.sku,
                    p.name,
                    p.name AS part,
                    p.category,
                    COALESCE(p.criticality, 'Essential') AS criticality,
                    COALESCE(p.unit_cost, 0.0) AS unit_cost,
                    COALESCE(i.quantity, 0) AS quantity,
                    COALESCE(i.quantity, 0) AS "currentStock",
                    COALESCE(i.reorder_point, 0) AS reorder_point,
                    COALESCE(i.reorder_point, 0) AS "reorderPoint",
                    COALESCE(i.safety_stock, 0) AS safety_stock,
                    COALESCE(i.safety_stock, 0) AS "safetyStock",
                    COALESCE(i.max_stock, 0) AS max_stock,
                    COALESCE(i.max_stock, 0) AS "maxStock",
                    i.updated_at
                   FROM parts p
                   LEFT JOIN inventory i ON i.part_id = p.id
                   ORDER BY p.name ASC"""
            ).fetchall()

            results = []
            for r in rows:
                item = dict(r)
                qty = item["quantity"]
                safety = item["safety_stock"]
                reorder = item["reorder_point"]

                # Calculate status and stockout risk
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
                results.append(item)
            return results
    except Exception as e:
        logger.error(f"Error fetching inventory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch inventory stock levels.")


@router.get("/inventory/{part_id}", response_model=InventoryItemResponse)
def get_inventory_for_part(part_id: int):
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT 
                    i.id,
                    p.id AS part_id,
                    p.sku,
                    p.name,
                    p.name AS part,
                    p.category,
                    COALESCE(p.criticality, 'Essential') AS criticality,
                    COALESCE(p.unit_cost, 0.0) AS unit_cost,
                    COALESCE(i.quantity, 0) AS quantity,
                    COALESCE(i.quantity, 0) AS "currentStock",
                    COALESCE(i.reorder_point, 0) AS reorder_point,
                    COALESCE(i.reorder_point, 0) AS "reorderPoint",
                    COALESCE(i.safety_stock, 0) AS safety_stock,
                    COALESCE(i.safety_stock, 0) AS "safetyStock",
                    COALESCE(i.max_stock, 0) AS max_stock,
                    COALESCE(i.max_stock, 0) AS "maxStock",
                    i.updated_at
                   FROM parts p
                   LEFT JOIN inventory i ON i.part_id = p.id
                   WHERE p.id = %s""",
                (part_id,),
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"Inventory for part id {part_id} not found.")

            item = dict(row)
            qty = item["quantity"]
            safety = item["safety_stock"]
            reorder = item["reorder_point"]

            if qty <= safety:
                item["status"] = "Critical"
                item["stockoutRisk"] = "High"
            elif qty <= reorder:
                item["status"] = "Warning"
                item["stockoutRisk"] = "Medium"
            else:
                item["status"] = "Healthy"
                item["stockoutRisk"] = "Low"

            item["depot"] = DEPOT_NAME
            item["daysOfSupply"] = max(1, round(qty / 3)) if qty > 0 else 0
            return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching inventory for part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch part inventory.")


@router.put("/inventory/{part_id}", response_model=InventoryItemResponse, dependencies=[Depends(verify_api_key)])
def update_inventory(part_id: int, payload: InventoryUpdate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Verify part exists
                part = conn.execute("SELECT * FROM parts WHERE id = %s", (part_id,)).fetchone()
                if not part:
                    raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")

                existing = conn.execute("SELECT * FROM inventory WHERE part_id = %s", (part_id,)).fetchone()
                old_qty = existing["quantity"] if existing else 0

                qty = payload.quantity if payload.quantity is not None else (existing["quantity"] if existing else 0)
                reorder = payload.reorder_point if payload.reorder_point is not None else (existing["reorder_point"] if existing else 10)
                safety = payload.safety_stock if payload.safety_stock is not None else (existing["safety_stock"] if existing else 5)
                max_stk = payload.max_stock if payload.max_stock is not None else (existing["max_stock"] if existing else 50)

                updated = conn.execute(
                    """INSERT INTO inventory (part_id, quantity, reorder_point, safety_stock, max_stock, updated_at)
                       VALUES (%s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (part_id) DO UPDATE
                       SET quantity = EXCLUDED.quantity,
                           reorder_point = EXCLUDED.reorder_point,
                           safety_stock = EXCLUDED.safety_stock,
                           max_stock = EXCLUDED.max_stock,
                           updated_at = NOW()
                       RETURNING *""",
                    (part_id, qty, reorder, safety, max_stk),
                ).fetchone()

                # If quantity changed manually, record an ADJUSTMENT transaction
                qty_diff = qty - old_qty
                if qty_diff != 0:
                    conn.execute(
                        """INSERT INTO inventory_transactions 
                           (part_id, transaction_type, quantity, reference_type, reference_id, notes)
                           VALUES (%s, 'ADJUSTMENT', %s, 'MANUAL_AUDIT', 'STOCK_UPDATE', 'Manual stock level adjustment')""",
                        (part_id, qty_diff),
                    )

                return get_inventory_for_part(part_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating inventory for part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update inventory.")


# =====================================================================
# 4. Suppliers Endpoints
# =====================================================================
@router.get("/suppliers", response_model=List[SupplierResponse])
def get_suppliers(status: Optional[str] = None, category: Optional[str] = None):
    try:
        query = "SELECT * FROM suppliers WHERE 1=1"
        params = []
        if status:
            query += " AND LOWER(status) = LOWER(%s)"
            params.append(status)
        if category:
            query += " AND LOWER(category) = LOWER(%s)"
            params.append(category)
        query += " ORDER BY supplier_name ASC"

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["name"] = item["supplier_name"]
                item["avgLeadTimeDays"] = item["lead_time_days"]
                item["contactEmail"] = item.get("email")
                item["contactPhone"] = item.get("phone")
                results.append(item)
            return results
    except Exception as e:
        logger.error(f"Error fetching suppliers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch suppliers.")


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier_by_id(supplier_id: int):
    try:
        with get_db_connection() as conn:
            supplier = conn.execute("SELECT * FROM suppliers WHERE id = %s", (supplier_id,)).fetchone()
            if not supplier:
                raise HTTPException(status_code=404, detail=f"Supplier with id {supplier_id} not found.")
            item = dict(supplier)
            item["name"] = item["supplier_name"]
            item["avgLeadTimeDays"] = item["lead_time_days"]
            item["contactEmail"] = item.get("email")
            item["contactPhone"] = item.get("phone")
            return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching supplier {supplier_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch supplier.")


@router.post("/suppliers", response_model=SupplierResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_supplier(payload: SupplierCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """INSERT INTO suppliers 
                       (supplier_code, supplier_name, contact_person, email, phone, category, lead_time_days, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING *""",
                    (
                        payload.supplier_code.strip(),
                        payload.supplier_name.strip(),
                        payload.contact_person,
                        payload.email,
                        payload.phone,
                        payload.category,
                        payload.lead_time_days,
                        payload.status,
                    ),
                ).fetchone()
                item = dict(row)
                item["name"] = item["supplier_name"]
                item["avgLeadTimeDays"] = item["lead_time_days"]
                item["contactEmail"] = item.get("email")
                item["contactPhone"] = item.get("phone")
                return item
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"Supplier code '{payload.supplier_code}' already exists.")
    except Exception as e:
        logger.error(f"Error creating supplier: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create supplier.")


@router.put("/suppliers/{supplier_id}", response_model=SupplierResponse, dependencies=[Depends(verify_api_key)])
def update_supplier(supplier_id: int, payload: SupplierUpdate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                existing = conn.execute("SELECT * FROM suppliers WHERE id = %s", (supplier_id,)).fetchone()
                if not existing:
                    raise HTTPException(status_code=404, detail=f"Supplier with id {supplier_id} not found.")

                update_data = payload.model_dump(exclude_unset=True)
                if not update_data:
                    item = dict(existing)
                    item["name"] = item["supplier_name"]
                    item["avgLeadTimeDays"] = item["lead_time_days"]
                    item["contactEmail"] = item.get("email")
                    item["contactPhone"] = item.get("phone")
                    return item

                set_clauses = [f"{k} = %s" for k in update_data.keys()]
                values = list(update_data.values())
                values.append(supplier_id)

                query = f"UPDATE suppliers SET {', '.join(set_clauses)} WHERE id = %s RETURNING *"
                updated = conn.execute(query, values).fetchone()
                item = dict(updated)
                item["name"] = item["supplier_name"]
                item["avgLeadTimeDays"] = item["lead_time_days"]
                item["contactEmail"] = item.get("email")
                item["contactPhone"] = item.get("phone")
                return item
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Supplier code already in use.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating supplier {supplier_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update supplier.")


@router.delete("/suppliers/{supplier_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_supplier(supplier_id: int):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                deleted = conn.execute("DELETE FROM suppliers WHERE id = %s RETURNING id", (supplier_id,)).fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail=f"Supplier with id {supplier_id} not found.")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting supplier {supplier_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete supplier.")


# =====================================================================
# 5. Supplier Parts Endpoints (PuLP optimization link)
# =====================================================================
@router.get("/supplier-parts", response_model=List[SupplierPartResponse])
def get_supplier_parts(supplier_id: Optional[int] = None, part_id: Optional[int] = None):
    try:
        query = """
            SELECT 
                sp.id,
                sp.supplier_id,
                s.supplier_name,
                s.supplier_code,
                sp.part_id,
                p.name AS part_name,
                p.sku,
                sp.supplier_unit_cost,
                sp.lead_time_days,
                sp.minimum_order_quantity
            FROM supplier_parts sp
            JOIN suppliers s ON s.id = sp.supplier_id
            JOIN parts p ON p.id = sp.part_id
            WHERE 1=1
        """
        params = []
        if supplier_id:
            query += " AND sp.supplier_id = %s"
            params.append(supplier_id)
        if part_id:
            query += " AND sp.part_id = %s"
            params.append(part_id)
        query += " ORDER BY s.supplier_name, p.name"

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching supplier-part mappings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch supplier-part mappings.")


@router.post("/supplier-parts", response_model=SupplierPartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_or_update_supplier_part(payload: SupplierPartCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Verify part and supplier exist
                p = conn.execute("SELECT id FROM parts WHERE id = %s", (payload.part_id,)).fetchone()
                if not p:
                    raise HTTPException(status_code=404, detail="Part not found.")
                s = conn.execute("SELECT id FROM suppliers WHERE id = %s", (payload.supplier_id,)).fetchone()
                if not s:
                    raise HTTPException(status_code=404, detail="Supplier not found.")

                row = conn.execute(
                    """INSERT INTO supplier_parts 
                       (supplier_id, part_id, supplier_unit_cost, lead_time_days, minimum_order_quantity)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (supplier_id, part_id) DO UPDATE
                       SET supplier_unit_cost = EXCLUDED.supplier_unit_cost,
                           lead_time_days = EXCLUDED.lead_time_days,
                           minimum_order_quantity = EXCLUDED.minimum_order_quantity
                       RETURNING id""",
                    (
                        payload.supplier_id,
                        payload.part_id,
                        payload.supplier_unit_cost,
                        payload.lead_time_days,
                        payload.minimum_order_quantity,
                    ),
                ).fetchone()

                # Fetch full enriched response
                enriched = conn.execute(
                    """SELECT 
                        sp.id, sp.supplier_id, s.supplier_name, s.supplier_code,
                        sp.part_id, p.name AS part_name, p.sku,
                        sp.supplier_unit_cost, sp.lead_time_days, sp.minimum_order_quantity
                       FROM supplier_parts sp
                       JOIN suppliers s ON s.id = sp.supplier_id
                       JOIN parts p ON p.id = sp.part_id
                       WHERE sp.id = %s""",
                    (row["id"],),
                ).fetchone()
                return dict(enriched)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating supplier part: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to link supplier and part.")


# =====================================================================
# 6. Purchase Orders Endpoints
# =====================================================================
def _build_po_response(po_row: dict, items: list) -> PurchaseOrderResponse:
    item_responses = []
    total_calc = 0.0
    for it in items:
        tot = float(it["quantity"]) * float(it["unit_cost"])
        total_calc += tot
        item_responses.append(
            PurchaseOrderItemResponse(
                id=it["id"],
                purchase_order_id=it["purchase_order_id"],
                part_id=it["part_id"],
                part_name=it.get("part_name"),
                sku=it.get("sku"),
                quantity=it["quantity"],
                unit_cost=float(it["unit_cost"]),
                received_quantity=it.get("received_quantity", 0),
                total_cost=tot,
                part=it.get("part_name"),
                unitPrice=float(it["unit_cost"]),
                receivedQuantity=it.get("received_quantity", 0),
            )
        )

    tot_val = float(po_row.get("total_value") or total_calc)
    order_dt = po_row.get("order_date") or po_row.get("created_at")
    exp_dt = po_row.get("expected_date")

    return PurchaseOrderResponse(
        id=po_row["id"],
        po_number=po_row["po_number"],
        poNumber=po_row["po_number"],
        supplier_id=po_row.get("supplier_id"),
        supplier_name=po_row.get("supplier_name"),
        supplier=po_row.get("supplier_name") or "Primary Vendor",
        depot=DEPOT_NAME,
        status=po_row["status"],
        order_date=order_dt,
        poDate=order_dt.strftime("%Y-%m-%d") if order_dt else None,
        expected_date=exp_dt,
        expectedDelivery=exp_dt.strftime("%Y-%m-%d") if exp_dt else None,
        received_date=po_row.get("received_date"),
        total_value=tot_val,
        total=tot_val,
        created_at=po_row["created_at"],
        items=item_responses,
        lines=item_responses,
    )


@router.get("/purchase-orders", response_model=List[PurchaseOrderResponse])
def get_purchase_orders(status: Optional[str] = None):
    try:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    po.*,
                    s.supplier_name
                FROM purchase_orders po
                LEFT JOIN suppliers s ON s.id = po.supplier_id
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND LOWER(po.status) = LOWER(%s)"
                params.append(status)
            query += " ORDER BY po.id DESC"

            orders = conn.execute(query, params).fetchall()
            if not orders:
                return []

            po_ids = [o["id"] for o in orders]
            # Fetch all items for these POs in one batch
            items_query = """
                SELECT 
                    poi.*,
                    p.name AS part_name,
                    p.sku
                FROM purchase_order_items poi
                JOIN parts p ON p.id = poi.part_id
                WHERE poi.purchase_order_id = ANY(%s)
                ORDER BY poi.id ASC
            """
            all_items = conn.execute(items_query, (po_ids,)).fetchall()

            # Group items by purchase_order_id
            items_map: dict[int, list] = {oid: [] for oid in po_ids}
            for it in all_items:
                items_map[it["purchase_order_id"]].append(dict(it))

            return [_build_po_response(dict(o), items_map[o["id"]]) for o in orders]
    except Exception as e:
        logger.error(f"Error fetching purchase orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch purchase orders.")


@router.get("/purchase-orders/{id_or_number}", response_model=PurchaseOrderResponse)
def get_purchase_order(id_or_number: str):
    try:
        with get_db_connection() as conn:
            if id_or_number.isdigit():
                po = conn.execute(
                    """SELECT po.*, s.supplier_name 
                       FROM purchase_orders po 
                       LEFT JOIN suppliers s ON s.id = po.supplier_id 
                       WHERE po.id = %s""",
                    (int(id_or_number),),
                ).fetchone()
            else:
                po = conn.execute(
                    """SELECT po.*, s.supplier_name 
                       FROM purchase_orders po 
                       LEFT JOIN suppliers s ON s.id = po.supplier_id 
                       WHERE po.po_number = %s""",
                    (id_or_number,),
                ).fetchone()

            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found.")

            items = conn.execute(
                """SELECT poi.*, p.name AS part_name, p.sku
                   FROM purchase_order_items poi
                   JOIN parts p ON p.id = poi.part_id
                   WHERE poi.purchase_order_id = %s
                   ORDER BY poi.id ASC""",
                (po["id"],),
            ).fetchall()

            return _build_po_response(dict(po), [dict(it) for it in items])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching purchase order {id_or_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch purchase order.")


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_purchase_order(payload: PurchaseOrderCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # 1. Resolve supplier
                supplier_id = payload.supplier_id
                if not supplier_id and payload.supplier:
                    # Lookup supplier by name or code
                    supp = conn.execute(
                        "SELECT id FROM suppliers WHERE LOWER(supplier_name) = LOWER(%s) OR LOWER(supplier_code) = LOWER(%s) LIMIT 1",
                        (payload.supplier.strip(), payload.supplier.strip()),
                    ).fetchone()
                    if supp:
                        supplier_id = supp["id"]

                # 2. Determine or generate PO Number
                po_num = payload.po_number
                if not po_num:
                    year = datetime.now().year
                    seq = conn.execute("SELECT COUNT(*) + 1 AS count FROM purchase_orders").fetchone()["count"]
                    po_num = f"PO-{year}-{seq:04d}"

                # 3. Assemble items: support multi-item list or legacy single-item payload
                items_to_create = list(payload.items)
                if not items_to_create and payload.part_id and payload.quantity:
                    unit_c = payload.unit_cost
                    if unit_c is None:
                        p_cost = conn.execute("SELECT unit_cost FROM parts WHERE id = %s", (payload.part_id,)).fetchone()
                        unit_c = float(p_cost["unit_cost"]) if p_cost else 0.0
                    items_to_create.append(PurchaseOrderItemCreate(part_id=payload.part_id, quantity=payload.quantity, unit_cost=unit_c))

                if not items_to_create:
                    raise HTTPException(status_code=400, detail="Purchase order must contain at least one line item.")

                # Calculate total
                total_val = sum(it.quantity * it.unit_cost for it in items_to_create)

                # 4. Insert PO record
                order_dt = payload.order_date or datetime.now(timezone.utc)
                po_record = conn.execute(
                    """INSERT INTO purchase_orders 
                       (po_number, supplier_id, status, order_date, expected_date, total_value)
                       VALUES (%s, %s, 'Draft', %s, %s, %s)
                       RETURNING *""",
                    (po_num, supplier_id, order_dt, payload.expected_date, total_val),
                ).fetchone()

                # 5. Insert line items
                created_items = []
                for it in items_to_create:
                    # Validate part exists
                    part = conn.execute("SELECT id, name, sku FROM parts WHERE id = %s", (it.part_id,)).fetchone()
                    if not part:
                        raise HTTPException(status_code=404, detail=f"Part with id {it.part_id} not found.")

                    item_row = conn.execute(
                        """INSERT INTO purchase_order_items (purchase_order_id, part_id, quantity, unit_cost, received_quantity)
                           VALUES (%s, %s, %s, %s, 0)
                           RETURNING *""",
                        (po_record["id"], it.part_id, it.quantity, it.unit_cost),
                    ).fetchone()

                    item_dict = dict(item_row)
                    item_dict["part_name"] = part["name"]
                    item_dict["sku"] = part["sku"]
                    created_items.append(item_dict)

                # 6. Fetch supplier name if exists
                supp_name = None
                if supplier_id:
                    s_row = conn.execute("SELECT supplier_name FROM suppliers WHERE id = %s", (supplier_id,)).fetchone()
                    if s_row:
                        supp_name = s_row["supplier_name"]

                po_dict = dict(po_record)
                po_dict["supplier_name"] = supp_name
                return _build_po_response(po_dict, created_items)
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"Purchase order number '{payload.po_number}' already exists.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating purchase order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create purchase order.")


@router.put("/purchase-orders/{id_or_number}", response_model=PurchaseOrderResponse, dependencies=[Depends(verify_api_key)])
def update_purchase_order(id_or_number: str, payload: PurchaseOrderUpdate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                where_clause = "id = %s" if id_or_number.isdigit() else "po_number = %s"
                val = int(id_or_number) if id_or_number.isdigit() else id_or_number
                po = conn.execute(f"SELECT * FROM purchase_orders WHERE {where_clause}", (val,)).fetchone()
                if not po:
                    raise HTTPException(status_code=404, detail="Purchase order not found.")

                update_data = payload.model_dump(exclude_unset=True)
                if update_data:
                    set_clauses = [f"{k} = %s" for k in update_data.keys()]
                    vals = list(update_data.values())
                    vals.append(po["id"])
                    conn.execute(f"UPDATE purchase_orders SET {', '.join(set_clauses)} WHERE id = %s", vals)

                return get_purchase_order(str(po["id"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating purchase order {id_or_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update purchase order.")


@router.patch("/purchase-orders/{id_or_number}/status", response_model=PurchaseOrderResponse, dependencies=[Depends(verify_api_key)])
def update_purchase_order_status(id_or_number: str, payload: PurchaseOrderStatusUpdate):
    """
    CRITICAL BUSINESS LOGIC:
    When a Purchase Order status changes to 'received' / 'Received':
    - Atomically update all items to received_quantity = quantity
    - Atomically increase inventory stock quantity for each part
    - Atomically create an inventory_transactions audit record
    - Atomically update PO received_date and status to 'Received'
    All enclosed in a single database transaction with row locks to prevent race conditions.
    """
    target_status = payload.status.capitalize()
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                where_clause = "id = %s" if id_or_number.isdigit() else "po_number = %s"
                val = int(id_or_number) if id_or_number.isdigit() else id_or_number

                # Lock PO row
                po = conn.execute(
                    f"SELECT * FROM purchase_orders WHERE {where_clause} FOR UPDATE",
                    (val,),
                ).fetchone()

                if not po:
                    raise HTTPException(status_code=404, detail="Purchase order not found.")

                curr_status = po["status"].capitalize()

                if curr_status == target_status:
                    return get_purchase_order(str(po["id"]))

                if curr_status in ("Received", "Cancelled") and target_status in ("Received", "Draft"):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cannot change status of an already '{curr_status}' purchase order.",
                    )

                if target_status == "Received":
                    # Fetch all items for this PO
                    items = conn.execute(
                        "SELECT * FROM purchase_order_items WHERE purchase_order_id = %s FOR UPDATE",
                        (po["id"],),
                    ).fetchall()

                    # Handle legacy POs that may not have items in purchase_order_items table
                    if not items:
                        # Check if legacy PO columns exist
                        if "part_id" in po and po["part_id"]:
                            items = [{"part_id": po["part_id"], "quantity": po.get("quantity", 0), "id": 0}]

                    for item in items:
                        part_id = item["part_id"]
                        qty_ordered = item["quantity"]
                        qty_already_received = item.get("received_quantity", 0)
                        qty_to_add = max(0, qty_ordered - qty_already_received)

                        if qty_to_add > 0:
                            # 1. Update inventory
                            conn.execute(
                                """INSERT INTO inventory (part_id, quantity, reorder_point, safety_stock, max_stock, updated_at)
                                   VALUES (%s, %s, 10, 5, 50, NOW())
                                   ON CONFLICT (part_id) DO UPDATE
                                   SET quantity = inventory.quantity + EXCLUDED.quantity,
                                       updated_at = NOW()""",
                                (part_id, qty_to_add),
                            )

                            # 2. Record inventory transaction audit record
                            conn.execute(
                                """INSERT INTO inventory_transactions 
                                   (part_id, transaction_type, quantity, reference_type, reference_id, transaction_date, notes)
                                   VALUES (%s, 'PO_RECEIPT', %s, 'PURCHASE_ORDER', %s, NOW(), %s)""",
                                (
                                    part_id,
                                    qty_to_add,
                                    po["po_number"],
                                    f"Receipt of {qty_to_add} units from Purchase Order {po['po_number']}",
                                ),
                            )

                            # 3. Update received quantity on PO line
                            if item.get("id"):
                                conn.execute(
                                    "UPDATE purchase_order_items SET received_quantity = quantity WHERE id = %s",
                                    (item["id"],),
                                )

                    # 4. Mark PO received
                    conn.execute(
                        """UPDATE purchase_orders 
                           SET status = 'Received', received_date = NOW()
                           WHERE id = %s""",
                        (po["id"],),
                    )
                else:
                    # Update status normally (e.g. Ordered, Draft, Cancelled)
                    conn.execute(
                        "UPDATE purchase_orders SET status = %s WHERE id = %s",
                        (target_status, po["id"]),
                    )

                return get_purchase_order(str(po["id"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating PO status {id_or_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update purchase order status.")


# =====================================================================
# 7. Inventory Transactions Audit Trail
# =====================================================================
@router.get("/inventory-transactions", response_model=List[InventoryTransactionResponse])
def get_inventory_transactions(
    part_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    try:
        query = """
            SELECT 
                it.*,
                p.name AS part_name,
                p.sku
            FROM inventory_transactions it
            JOIN parts p ON p.id = it.part_id
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
    except Exception as e:
        logger.error(f"Error fetching inventory transactions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch inventory transactions.")


@router.post("/inventory-transactions", response_model=InventoryTransactionResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_inventory_transaction(payload: InventoryTransactionCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Verify part exists
                part = conn.execute("SELECT id, name, sku FROM parts WHERE id = %s", (payload.part_id,)).fetchone()
                if not part:
                    raise HTTPException(status_code=404, detail="Part not found.")

                # Insert transaction
                tx = conn.execute(
                    """INSERT INTO inventory_transactions 
                       (part_id, transaction_type, quantity, reference_type, reference_id, notes)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING *""",
                    (
                        payload.part_id,
                        payload.transaction_type,
                        payload.quantity,
                        payload.reference_type,
                        payload.reference_id,
                        payload.notes,
                    ),
                ).fetchone()

                # Adjust inventory stock accordingly
                conn.execute(
                    """INSERT INTO inventory (part_id, quantity, reorder_point, safety_stock, max_stock, updated_at)
                       VALUES (%s, GREATEST(0, %s), 10, 5, 50, NOW())
                       ON CONFLICT (part_id) DO UPDATE
                       SET quantity = GREATEST(0, inventory.quantity + %s),
                           updated_at = NOW()""",
                    (payload.part_id, payload.quantity, payload.quantity),
                )

                item = dict(tx)
                item["part_name"] = part["name"]
                item["sku"] = part["sku"]
                return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating inventory transaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record inventory transaction.")


# =====================================================================
# 8. Demand History Endpoints (For XGBoost & Forecasting)
# =====================================================================
@router.get("/demand-history", response_model=List[DemandHistoryResponse])
def get_demand_history(
    part_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    try:
        query = """
            SELECT 
                dh.*,
                p.sku,
                p.name AS part_name
            FROM demand_history dh
            JOIN parts p ON p.id = dh.part_id
            WHERE 1=1
        """
        params = []
        if part_id:
            query += " AND dh.part_id = %s"
            params.append(part_id)
        if start_date:
            query += " AND dh.date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND dh.date <= %s"
            params.append(end_date)
        query += " ORDER BY dh.date DESC, p.name ASC LIMIT %s"
        params.append(limit)

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching demand history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch demand history.")


@router.post("/demand-history", response_model=DemandHistoryResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def record_demand(payload: DemandHistoryCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Verify part
                part = conn.execute("SELECT id, sku, name FROM parts WHERE id = %s", (payload.part_id,)).fetchone()
                if not part:
                    raise HTTPException(status_code=404, detail="Part not found.")

                row = conn.execute(
                    """INSERT INTO demand_history (part_id, date, quantity_consumed, depot)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (part_id, date, depot) DO UPDATE
                       SET quantity_consumed = EXCLUDED.quantity_consumed
                       RETURNING *""",
                    (payload.part_id, payload.date, payload.quantity_consumed, payload.depot),
                ).fetchone()

                item = dict(row)
                item["sku"] = part["sku"]
                item["part_name"] = part["name"]
                return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording demand: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record demand history.")


@router.post("/demand-history/batch", status_code=201, dependencies=[Depends(verify_api_key)])
def record_demand_batch(payload: DemandHistoryBatchCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                inserted_count = 0
                for rec in payload.records:
                    conn.execute(
                        """INSERT INTO demand_history (part_id, date, quantity_consumed, depot)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (part_id, date, depot) DO UPDATE
                           SET quantity_consumed = EXCLUDED.quantity_consumed""",
                        (rec.part_id, rec.date, rec.quantity_consumed, rec.depot),
                    )
                    inserted_count += 1
                return {"status": "ok", "records_processed": inserted_count}
    except Exception as e:
        logger.error(f"Error inserting demand batch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to insert demand batch.")


# =====================================================================
# 9. Forecasts Endpoints (Consumed and generated by ML)
# =====================================================================
@router.get("/forecasts", response_model=List[ForecastResponse])
def get_forecasts(
    part_id: Optional[int] = None,
    model_name: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        query = """
            SELECT 
                f.*,
                p.sku,
                p.name AS part_name
            FROM forecasts f
            JOIN parts p ON p.id = f.part_id
            WHERE 1=1
        """
        params = []
        if part_id:
            query += " AND f.part_id = %s"
            params.append(part_id)
        if model_name:
            query += " AND LOWER(f.model_name) = LOWER(%s)"
            params.append(model_name)
        query += " ORDER BY f.forecast_date ASC, p.name ASC LIMIT %s"
        params.append(limit)

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching forecasts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch forecasts.")


@router.get("/forecasts/{part_id}", response_model=List[ForecastResponse])
def get_forecasts_for_part(part_id: int):
    return get_forecasts(part_id=part_id)


@router.post("/forecasts", status_code=201, dependencies=[Depends(verify_api_key)])
def store_forecasts(payload: ForecastCreate | ForecastBatchCreate):
    try:
        items = [payload] if isinstance(payload, ForecastCreate) else payload.records
        with get_db_connection() as conn:
            with conn.transaction():
                count = 0
                for f in items:
                    conn.execute(
                        """INSERT INTO forecasts (part_id, forecast_date, forecast_quantity, model_name, model_version)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (f.part_id, f.forecast_date, f.forecast_quantity, f.model_name, f.model_version),
                    )
                    count += 1
                return {"status": "ok", "forecasts_stored": count}
    except Exception as e:
        logger.error(f"Error saving forecasts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save forecasts.")


# =====================================================================
# 10. Procurement Recommendations Endpoints (PuLP Optimization)
# =====================================================================
@router.get("/procurement-recommendations", response_model=List[ProcurementRecommendationResponse])
def get_procurement_recommendations(
    priority: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    try:
        query = """
            SELECT 
                pr.*,
                p.sku,
                p.name AS part_name,
                p.category,
                s.supplier_name AS primary_supplier
            FROM procurement_recommendations pr
            JOIN parts p ON p.id = pr.part_id
            LEFT JOIN supplier_parts sp ON sp.part_id = p.id
            LEFT JOIN suppliers s ON s.id = sp.supplier_id
            WHERE 1=1
        """
        params = []
        if priority:
            query += " AND LOWER(pr.priority) = LOWER(%s)"
            params.append(priority)
        query += " ORDER BY pr.estimated_cost DESC LIMIT %s"
        params.append(limit)

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["part"] = item["part_name"]
                item["quantity"] = item["recommended_quantity"]
                item["unit_price"] = float(item["unit_cost"])
                item["total_cost"] = float(item["estimated_cost"])
                item["supplier"] = item.get("primary_supplier") or "Primary KSRTC Vendor"
                results.append(item)
            return results
    except Exception as e:
        logger.error(f"Error fetching procurement recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch procurement recommendations.")


@router.post("/procurement-recommendations", status_code=201, dependencies=[Depends(verify_api_key)])
def store_procurement_recommendations(payload: ProcurementRecommendationCreate | ProcurementRecommendationBatchCreate):
    try:
        items = [payload] if isinstance(payload, ProcurementRecommendationCreate) else payload.recommendations
        with get_db_connection() as conn:
            with conn.transaction():
                count = 0
                for rec in items:
                    est_cost = rec.estimated_cost
                    if est_cost is None:
                        est_cost = rec.recommended_quantity * rec.unit_cost

                    conn.execute(
                        """INSERT INTO procurement_recommendations 
                           (part_id, recommended_quantity, unit_cost, estimated_cost, priority, reason, model_name)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            rec.part_id,
                            rec.recommended_quantity,
                            rec.unit_cost,
                            est_cost,
                            rec.priority,
                            rec.reason,
                            rec.model_name,
                        ),
                    )
                    count += 1
                return {"status": "ok", "recommendations_stored": count}
    except Exception as e:
        logger.error(f"Error storing procurement recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store recommendations.")


# =====================================================================
# 11. Model Runs Audit
# =====================================================================
@router.get("/model-runs", response_model=List[ModelRunResponse])
def get_model_runs(model_name: Optional[str] = None):
    try:
        query = "SELECT * FROM model_runs WHERE 1=1"
        params = []
        if model_name:
            query += " AND LOWER(model_name) = LOWER(%s)"
            params.append(model_name)
        query += " ORDER BY run_date DESC LIMIT 50"

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching model runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch model runs.")


@router.post("/model-runs", response_model=ModelRunResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def record_model_run(payload: ModelRunCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                import json
                row = conn.execute(
                    """INSERT INTO model_runs (model_name, model_version, status, metrics_json)
                       VALUES (%s, %s, %s, %s::jsonb)
                       RETURNING *""",
                    (payload.model_name, payload.model_version, payload.status, json.dumps(payload.metrics_json)),
                ).fetchone()
                return dict(row)
    except Exception as e:
        logger.error(f"Error recording model run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record model run.")


# =====================================================================
# 12. PuLP Optimization Unified Input & AI Analytics Context
# =====================================================================
@router.get("/procurement/optimization-input", response_model=PuLPOptimizationInputResponse)
def get_pulp_optimization_input():
    """
    Central Data Pipeline for PuLP Optimization Model:
    Returns unified data structure containing all parts, current on-hand stock,
    reorder points, safety stocks, forecasted demand, and supplier lead times/pricing.
    PuLP consumes this single endpoint to produce cost-optimal order quantities.
    """
    try:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    p.id AS part_id,
                    p.sku,
                    p.name,
                    p.category,
                    COALESCE(p.criticality, 'Essential') AS criticality,
                    COALESCE(i.quantity, 0) AS current_inventory,
                    COALESCE(i.reorder_point, 10) AS reorder_point,
                    COALESCE(i.safety_stock, 5) AS safety_stock,
                    COALESCE(i.max_stock, 50) AS max_stock,
                    COALESCE(latest_fc.forecast_quantity, 15.0) AS forecast_demand,
                    sp.supplier_id,
                    s.supplier_name,
                    COALESCE(sp.supplier_unit_cost, p.unit_cost) AS supplier_unit_cost,
                    COALESCE(sp.lead_time_days, s.lead_time_days, 7) AS lead_time_days,
                    COALESCE(sp.minimum_order_quantity, 1) AS minimum_order_quantity
                FROM parts p
                LEFT JOIN inventory i ON i.part_id = p.id
                LEFT JOIN LATERAL (
                    SELECT forecast_quantity 
                    FROM forecasts f 
                    WHERE f.part_id = p.id 
                    ORDER BY forecast_date DESC 
                    LIMIT 1
                ) latest_fc ON true
                LEFT JOIN LATERAL (
                    SELECT * FROM supplier_parts 
                    WHERE part_id = p.id 
                    ORDER BY supplier_unit_cost ASC 
                    LIMIT 1
                ) sp ON true
                LEFT JOIN suppliers s ON s.id = sp.supplier_id
                ORDER BY p.name ASC
            """
            rows = conn.execute(query).fetchall()
            items = [PuLPOptimizationInputItem(**dict(r)) for r in rows]

            return PuLPOptimizationInputResponse(
                depot=DEPOT_NAME,
                generated_at=datetime.now(timezone.utc),
                items=items,
            )
    except Exception as e:
        logger.error(f"Error fetching PuLP input: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to assemble PuLP optimization input.")


@router.get("/analytics/context")
def get_ai_analytics_context():
    """
    Unified context feed for Gemini AI Assistant:
    Provides current depot inventory health, open PO counts, budget recommendations,
    and supplier reliability metrics for prompt answering.
    """
    try:
        with get_db_connection() as conn:
            parts_count = conn.execute("SELECT COUNT(*) AS c FROM parts").fetchone()["c"]
            inv_stats = conn.execute(
                """SELECT 
                    COUNT(CASE WHEN COALESCE(i.quantity, 0) <= COALESCE(i.safety_stock, 0) THEN 1 END) AS critical_count,
                    COUNT(CASE WHEN COALESCE(i.quantity, 0) > COALESCE(i.safety_stock, 0) AND COALESCE(i.quantity, 0) <= COALESCE(i.reorder_point, 0) THEN 1 END) AS warning_count,
                    COUNT(CASE WHEN COALESCE(i.quantity, 0) > COALESCE(i.reorder_point, 0) THEN 1 END) AS healthy_count,
                    SUM(COALESCE(i.quantity, 0) * COALESCE(p.unit_cost, 0)) AS total_inventory_value
                   FROM parts p
                   LEFT JOIN inventory i ON i.part_id = p.id"""
            ).fetchone()

            po_stats = conn.execute(
                """SELECT 
                    COUNT(*) AS total_pos,
                    COUNT(CASE WHEN LOWER(status) IN ('draft', 'ordered') THEN 1 END) AS open_pos,
                    COALESCE(SUM(CASE WHEN LOWER(status) IN ('draft', 'ordered') THEN total_value ELSE 0 END), 0) AS open_po_value
                   FROM purchase_orders"""
            ).fetchone()

            rec_stats = conn.execute(
                """SELECT 
                    COUNT(*) AS rec_count,
                    COALESCE(SUM(estimated_cost), 0) AS total_recommended_spend
                   FROM procurement_recommendations"""
            ).fetchone()

            return {
                "depot": DEPOT_NAME,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_catalog_parts": parts_count,
                "inventory_summary": {
                    "critical_parts_count": inv_stats["critical_count"],
                    "warning_parts_count": inv_stats["warning_count"],
                    "healthy_parts_count": inv_stats["healthy_count"],
                    "total_inventory_value_inr": float(inv_stats["total_inventory_value"] or 0),
                },
                "purchase_orders_summary": {
                    "total_orders": po_stats["total_pos"],
                    "open_orders": po_stats["open_pos"],
                    "open_orders_value_inr": float(po_stats["open_po_value"]),
                },
                "procurement_optimization": {
                    "pending_recommendations_count": rec_stats["rec_count"],
                    "total_recommended_spend_inr": float(rec_stats["total_recommended_spend"]),
                },
            }
    except Exception as e:
        logger.error(f"Error assembling AI context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch AI analytics context.")


# =====================================================================
# 13. Database Seed Endpoint
# =====================================================================
@router.post("/seed", dependencies=[Depends(verify_api_key)])
def trigger_database_seed():
    """
    Executes database seeding with authentic KSRTC parts, inventory, suppliers,
    historical consumption (90 days), purchase orders, and PuLP recommendations.
    Safe to run repeatedly (idempotent).
    """
    try:
        from seed import seed_database
        seed_database()
        return {
            "status": "ok",
            "message": "Database seeded successfully with KSRTC Central Depot data.",
            "depot": DEPOT_NAME,
        }
    except Exception as e:
        logger.error(f"Error during seed trigger: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database seeding failed: {str(e)}")


# Root-level fallback aliases for flexible frontend base URLs (with or without /api/v1/db prefix)
@app.get("/inventory", include_in_schema=False)
@app.get("/inventory/inventory", include_in_schema=False)
def root_inventory():
    return get_inventory()

@app.get("/parts", include_in_schema=False)
def root_parts():
    return get_parts()

@app.get("/suppliers", include_in_schema=False)
def root_suppliers():
    return get_suppliers()

@app.get("/purchase-orders", include_in_schema=False)
def root_purchase_orders():
    return get_purchase_orders()


# Include the API router
app.include_router(router)
