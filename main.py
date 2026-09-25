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
    PurchaseOrderItemCreate,
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
    VendorCreate,
    VendorResponse,
    VendorUpdate,
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

DEPOT_NAME = "KSRTC Central Stores"


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


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error(f"Global unhandled exception on {request.method} {request.url}: {exc}", exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "detail": "Internal server error occurred.", "error_type": type(exc).__name__},
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


@router.get("/debug/schema")
def debug_schema():
    with get_db_connection() as conn:
        cols = conn.execute(
            """SELECT table_name, column_name, data_type 
               FROM information_schema.columns 
               WHERE table_schema = 'public'
               ORDER BY table_name, ordinal_position"""
        ).fetchall()
        return [dict(c) for c in cols]


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
# Actual Neon table: parts
# Columns: part_id, part_number, part_name, category, sub_category,
# description, unit_of_measure, criticality, vehicle_system, standard_cost,
# minimum_order_quantity, reorder_point, safety_stock, lead_time_days,
# annual_demand, active_status, created_date
# =====================================================================
def _build_part_dict(r: dict) -> dict:
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


@router.get("/parts", response_model=List[PartResponse])
def get_parts(
    category: Optional[str] = None,
    criticality: Optional[str] = None,
    search: Optional[str] = None,
):
    try:
        query = """
            SELECT 
                part_id, part_number, part_name, category, sub_category,
                description, unit_of_measure, criticality, vehicle_system,
                standard_cost, minimum_order_quantity, reorder_point,
                safety_stock, lead_time_days, annual_demand, active_status,
                created_date
            FROM parts 
            WHERE 1=1
        """
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
            return [_build_part_dict(dict(r)) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching parts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch parts catalog.")


@router.get("/parts/{part_id}", response_model=PartResponse)
def get_part_by_id(part_id: int):
    try:
        with get_db_connection() as conn:
            part = conn.execute("SELECT * FROM parts WHERE part_id = %s", (part_id,)).fetchone()
            if not part:
                raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")
            return _build_part_dict(dict(part))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch part.")


@router.post("/parts", response_model=PartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_part(payload: PartCreate):
    try:
        pnum = payload.part_number or payload.sku
        pname = payload.part_name or payload.name
        cost = payload.standard_cost if payload.standard_cost is not None else (payload.unit_cost or 0.0)

        with get_db_connection() as conn:
            with conn.transaction():
                part = conn.execute(
                    """INSERT INTO parts 
                       (part_number, part_name, category, sub_category, description, 
                        unit_of_measure, criticality, vehicle_system, standard_cost, 
                        minimum_order_quantity, reorder_point, safety_stock, 
                        lead_time_days, annual_demand, active_status, created_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       RETURNING *""",
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

                # Automatically initialize inventory record for newly created part
                conn.execute(
                    """INSERT INTO inventory 
                       (part_id, current_stock, reserved_stock, available_stock, stock_in_transit, 
                        reorder_point, safety_stock, maximum_stock, average_unit_cost, inventory_value, last_updated)
                       VALUES (%s, 0, 0, 0, 0, %s, %s, 50, %s, 0.0, NOW())
                       ON CONFLICT (part_id) DO NOTHING""",
                    (part["part_id"], payload.reorder_point or 10, payload.safety_stock or 5, cost),
                )
                return _build_part_dict(dict(part))
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"A part with part_number '{payload.part_number or payload.sku}' already exists.")
    except Exception as e:
        logger.error(f"Error creating part: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create part.")


@router.put("/parts/{part_id}", response_model=PartResponse, dependencies=[Depends(verify_api_key)])
def update_part(part_id: int, payload: PartUpdate):
    try:
        with get_db_connection() as conn:
            existing = conn.execute("SELECT * FROM parts WHERE part_id = %s", (part_id,)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail=f"Part with id {part_id} not found.")

            update_data = payload.model_dump(exclude_unset=True)
            if not update_data:
                return _build_part_dict(dict(existing))

            # Normalize alias fields to actual database columns
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
            updated = conn.execute(query, values).fetchone()
            conn.commit()
            return _build_part_dict(dict(updated))
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Part number already exists on another part.")
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
                deleted = conn.execute("DELETE FROM parts WHERE part_id = %s RETURNING part_id", (part_id,)).fetchone()
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
# Actual Neon schema: inventory
# Columns: inventory_id, part_id, current_stock, reserved_stock,
# available_stock, stock_in_transit, reorder_point, safety_stock,
# maximum_stock, average_unit_cost, inventory_value, last_receipt_date,
# last_issue_date, last_updated
# =====================================================================
def _build_inventory_dict(r: dict) -> dict:
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


@router.get("/inventory", response_model=List[InventoryItemResponse])
@router.get("/inventory/inventory", response_model=List[InventoryItemResponse], include_in_schema=False)
def get_inventory():
    try:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    COALESCE(i.inventory_id, p.part_id) AS id,
                    i.inventory_id,
                    p.part_id,
                    p.part_number,
                    p.part_number AS sku,
                    p.part_name,
                    p.part_name AS name,
                    p.part_name AS part,
                    p.category,
                    p.sub_category,
                    COALESCE(p.criticality, 'Essential') AS criticality,
                    COALESCE(p.standard_cost, 0.0) AS standard_cost,
                    COALESCE(p.standard_cost, 0.0) AS unit_cost,
                    COALESCE(i.average_unit_cost, p.standard_cost, 0.0) AS average_unit_cost,
                    COALESCE(i.current_stock, 0) AS current_stock,
                    COALESCE(i.current_stock, 0) AS quantity,
                    COALESCE(i.current_stock, 0) AS "currentStock",
                    COALESCE(i.reserved_stock, 0) AS reserved_stock,
                    COALESCE(i.available_stock, COALESCE(i.current_stock, 0) - COALESCE(i.reserved_stock, 0)) AS available_stock,
                    COALESCE(i.stock_in_transit, 0) AS stock_in_transit,
                    COALESCE(i.reorder_point, p.reorder_point, 10) AS reorder_point,
                    COALESCE(i.reorder_point, p.reorder_point, 10) AS "reorderPoint",
                    COALESCE(i.safety_stock, p.safety_stock, 5) AS safety_stock,
                    COALESCE(i.safety_stock, p.safety_stock, 5) AS "safetyStock",
                    COALESCE(i.maximum_stock, 50) AS maximum_stock,
                    COALESCE(i.maximum_stock, 50) AS max_stock,
                    COALESCE(i.maximum_stock, 50) AS "maxStock",
                    COALESCE(i.inventory_value, COALESCE(i.current_stock, 0) * COALESCE(p.standard_cost, 0.0)) AS inventory_value,
                    i.last_receipt_date,
                    i.last_issue_date,
                    COALESCE(i.last_updated, p.created_date, NOW()) AS last_updated,
                    COALESCE(i.last_updated, p.created_date, NOW()) AS updated_at
                FROM parts p
                LEFT JOIN inventory i ON i.part_id = p.part_id
                ORDER BY p.part_name ASC
            """
            rows = conn.execute(query).fetchall()
            return [_build_inventory_dict(dict(r)) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching inventory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch inventory: {type(e).__name__}: {str(e)}")


@router.get("/inventory/{part_id}", response_model=InventoryItemResponse)
def get_inventory_for_part(part_id: int):
    try:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    COALESCE(i.inventory_id, p.part_id) AS id,
                    i.inventory_id,
                    p.part_id,
                    p.part_number,
                    p.part_number AS sku,
                    p.part_name,
                    p.part_name AS name,
                    p.part_name AS part,
                    p.category,
                    p.sub_category,
                    COALESCE(p.criticality, 'Essential') AS criticality,
                    COALESCE(p.standard_cost, 0.0) AS standard_cost,
                    COALESCE(p.standard_cost, 0.0) AS unit_cost,
                    COALESCE(i.average_unit_cost, p.standard_cost, 0.0) AS average_unit_cost,
                    COALESCE(i.current_stock, 0) AS current_stock,
                    COALESCE(i.current_stock, 0) AS quantity,
                    COALESCE(i.current_stock, 0) AS "currentStock",
                    COALESCE(i.reserved_stock, 0) AS reserved_stock,
                    COALESCE(i.available_stock, COALESCE(i.current_stock, 0) - COALESCE(i.reserved_stock, 0)) AS available_stock,
                    COALESCE(i.stock_in_transit, 0) AS stock_in_transit,
                    COALESCE(i.reorder_point, p.reorder_point, 10) AS reorder_point,
                    COALESCE(i.reorder_point, p.reorder_point, 10) AS "reorderPoint",
                    COALESCE(i.safety_stock, p.safety_stock, 5) AS safety_stock,
                    COALESCE(i.safety_stock, p.safety_stock, 5) AS "safetyStock",
                    COALESCE(i.maximum_stock, 50) AS maximum_stock,
                    COALESCE(i.maximum_stock, 50) AS max_stock,
                    COALESCE(i.maximum_stock, 50) AS "maxStock",
                    COALESCE(i.inventory_value, COALESCE(i.current_stock, 0) * COALESCE(p.standard_cost, 0.0)) AS inventory_value,
                    i.last_receipt_date,
                    i.last_issue_date,
                    COALESCE(i.last_updated, p.created_date, NOW()) AS last_updated,
                    COALESCE(i.last_updated, p.created_date, NOW()) AS updated_at
                FROM parts p
                LEFT JOIN inventory i ON i.part_id = p.part_id
                WHERE p.part_id = %s
            """
            row = conn.execute(query, (part_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Inventory for part id {part_id} not found.")

            return _build_inventory_dict(dict(row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching inventory for part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch inventory for part: {type(e).__name__}: {str(e)}")


@router.put("/inventory/{part_id}", response_model=InventoryItemResponse, dependencies=[Depends(verify_api_key)])
def update_inventory(part_id: int, payload: InventoryUpdate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Verify part exists
                part = conn.execute("SELECT * FROM parts WHERE part_id = %s", (part_id,)).fetchone()
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
                    """INSERT INTO inventory 
                       (part_id, current_stock, reserved_stock, available_stock, stock_in_transit, 
                        reorder_point, safety_stock, maximum_stock, average_unit_cost, inventory_value, last_updated)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (part_id) DO UPDATE
                       SET current_stock = EXCLUDED.current_stock,
                           reserved_stock = EXCLUDED.reserved_stock,
                           available_stock = EXCLUDED.available_stock,
                           stock_in_transit = EXCLUDED.stock_in_transit,
                           reorder_point = EXCLUDED.reorder_point,
                           safety_stock = EXCLUDED.safety_stock,
                           maximum_stock = EXCLUDED.maximum_stock,
                           average_unit_cost = EXCLUDED.average_unit_cost,
                           inventory_value = EXCLUDED.inventory_value,
                           last_updated = NOW()""",
                    (part_id, cur_qty, res_stk, avail_stk, in_transit, reorder, safety, max_stk, avg_cost, inv_val),
                )

                # If physical stock changed manually, record an ADJUSTMENT transaction if table exists
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

                return get_inventory_for_part(part_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating inventory for part {part_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update inventory.")


# =====================================================================
# 4. Vendors (Suppliers) Endpoints
# Actual Neon schema: vendors
# Columns: vendor_id, vendor_code, vendor_name, city, state, country,
# contact_email, contact_phone, vendor_category, payment_terms_days,
# default_lead_time_days, rating, on_time_delivery_rate, quality_rating,
# active_status, vendor_since
# =====================================================================
def _build_vendor_dict(r: dict) -> dict:
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
    try:
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
            return [_build_vendor_dict(dict(r)) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching vendors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch vendors.")


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
def get_vendor_by_id(vendor_id: int):
    try:
        with get_db_connection() as conn:
            vendor = conn.execute("SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id,)).fetchone()
            if not vendor:
                raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found.")
            return _build_vendor_dict(dict(vendor))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vendor {vendor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch vendor.")


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier_by_id(supplier_id: int):
    return get_vendor_by_id(supplier_id)


@router.post("/vendors", response_model=VendorResponse, status_code=201, dependencies=[Depends(verify_api_key)])
@router.post("/suppliers", response_model=SupplierResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_vendor(payload: VendorCreate):
    try:
        vcode = payload.vendor_code or payload.supplier_code
        vname = payload.vendor_name or payload.supplier_name or payload.name
        email = payload.contact_email or payload.email or payload.contactEmail
        phone = payload.contact_phone or payload.phone or payload.contactPhone
        cat = payload.vendor_category or payload.category
        lead_time = payload.default_lead_time_days or payload.lead_time_days or payload.avgLeadTimeDays or 7
        stat = payload.active_status or payload.status or "Active"

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
                return _build_vendor_dict(dict(row))
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"Vendor code '{payload.vendor_code or payload.supplier_code}' already exists.")
    except Exception as e:
        logger.error(f"Error creating vendor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create vendor.")


@router.put("/vendors/{vendor_id}", response_model=VendorResponse, dependencies=[Depends(verify_api_key)])
def update_vendor(vendor_id: int, payload: VendorUpdate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                existing = conn.execute("SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id,)).fetchone()
                if not existing:
                    raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found.")

                update_data = payload.model_dump(exclude_unset=True)
                if not update_data:
                    return _build_vendor_dict(dict(existing))

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
                    elif k in ("contact_person",):
                        pass  # legacy column omitted in actual schema
                    else:
                        db_update[k] = v

                if db_update:
                    set_clauses = [f"{k} = %s" for k in db_update.keys()]
                    values = list(db_update.values())
                    values.append(vendor_id)
                    query = f"UPDATE vendors SET {', '.join(set_clauses)} WHERE vendor_id = %s RETURNING *"
                    updated = conn.execute(query, values).fetchone()
                    return _build_vendor_dict(dict(updated))
                return _build_vendor_dict(dict(existing))
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Vendor code already in use.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating vendor {vendor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update vendor.")


@router.put("/suppliers/{supplier_id}", response_model=SupplierResponse, dependencies=[Depends(verify_api_key)])
def update_supplier(supplier_id: int, payload: SupplierUpdate):
    return update_vendor(supplier_id, payload)


@router.delete("/vendors/{vendor_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_vendor(vendor_id: int):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                deleted = conn.execute("DELETE FROM vendors WHERE vendor_id = %s RETURNING vendor_id", (vendor_id,)).fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail=f"Vendor with id {vendor_id} not found.")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting vendor {vendor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete vendor.")


@router.delete("/suppliers/{supplier_id}", status_code=204, dependencies=[Depends(verify_api_key)])
def delete_supplier(supplier_id: int):
    return delete_vendor(supplier_id)


# =====================================================================
# 5. Vendor / Supplier Parts (PuLP optimization mappings)
# =====================================================================
@router.get("/vendor-parts", response_model=List[SupplierPartResponse])
@router.get("/supplier-parts", response_model=List[SupplierPartResponse])
def get_supplier_parts(supplier_id: Optional[int] = None, vendor_id: Optional[int] = None, part_id: Optional[int] = None):
    target_vid = vendor_id or supplier_id
    try:
        with get_db_connection() as conn:
            # Check if a dedicated vendor_parts / supplier_parts table exists
            has_table = conn.execute(
                """SELECT table_name FROM information_schema.tables 
                   WHERE table_name IN ('supplier_parts', 'vendor_parts')"""
            ).fetchone()

            if has_table and has_table.get("table_name") == "supplier_parts":
                query = """
                    SELECT 
                        sp.id, sp.supplier_id, sp.supplier_id AS vendor_id,
                        s.vendor_name, s.vendor_name AS supplier_name,
                        s.vendor_code, s.vendor_code AS supplier_code,
                        sp.part_id, p.part_name, p.part_number, p.part_number AS sku,
                        sp.supplier_unit_cost, sp.supplier_unit_cost AS vendor_unit_cost,
                        sp.lead_time_days, sp.minimum_order_quantity
                    FROM supplier_parts sp
                    JOIN vendors s ON s.vendor_id = sp.supplier_id
                    JOIN parts p ON p.part_id = sp.part_id
                    WHERE 1=1
                """
                params = []
                if target_vid:
                    query += " AND sp.supplier_id = %s"
                    params.append(target_vid)
                if part_id:
                    query += " AND sp.part_id = %s"
                    params.append(part_id)
                query += " ORDER BY s.vendor_name, p.part_name"
                rows = conn.execute(query, params).fetchall()
                return [dict(r) for r in rows]

            # Derive mappings cleanly from purchase_order_items + purchase_orders + vendors + parts
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
    except Exception as e:
        logger.error(f"Error fetching vendor parts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch vendor-part mappings.")


@router.post("/vendor-parts", response_model=SupplierPartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
@router.post("/supplier-parts", response_model=SupplierPartResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_or_update_supplier_part(payload: SupplierPartCreate):
    vid = payload.vendor_id or payload.supplier_id
    cost = payload.unit_price if payload.unit_price is not None else payload.supplier_unit_cost
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Ensure part and vendor exist
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating supplier part: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to link supplier and part.")


# =====================================================================
# 6. Purchase Orders Endpoints
# Actual Neon schema:
# purchase_orders: po_id, po_number, vendor_id, po_date,
#   expected_delivery_date, actual_delivery_date, status, payment_terms,
#   currency, total_order_value, created_by
# purchase_order_items: po_item_id, po_id, part_id, ordered_quantity,
#   unit_price, discount_percentage, tax_percentage, line_total,
#   received_quantity, pending_quantity, item_status
# =====================================================================
def _build_po_response(po_row: dict, items: list) -> PurchaseOrderResponse:
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


@router.get("/purchase-orders", response_model=List[PurchaseOrderResponse])
def get_purchase_orders(status: Optional[str] = None):
    try:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    po.po_id,
                    po.po_id AS id,
                    po.po_number,
                    po.vendor_id,
                    po.vendor_id AS supplier_id,
                    po.po_date,
                    po.po_date AS order_date,
                    po.expected_delivery_date,
                    po.expected_delivery_date AS expected_date,
                    po.actual_delivery_date,
                    po.actual_delivery_date AS received_date,
                    po.status,
                    po.payment_terms,
                    po.currency,
                    po.total_order_value,
                    po.total_order_value AS total_value,
                    po.created_by,
                    v.vendor_name,
                    v.vendor_name AS supplier_name
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
            # Fetch all items for these POs in one batch
            items_query = """
                SELECT 
                    poi.po_item_id,
                    poi.po_item_id AS id,
                    poi.po_id,
                    poi.po_id AS purchase_order_id,
                    poi.part_id,
                    poi.ordered_quantity,
                    poi.ordered_quantity AS quantity,
                    poi.unit_price,
                    poi.unit_price AS unit_cost,
                    poi.discount_percentage,
                    poi.tax_percentage,
                    poi.line_total,
                    poi.line_total AS total_cost,
                    poi.received_quantity,
                    poi.pending_quantity,
                    poi.item_status,
                    p.part_name,
                    p.part_name AS name,
                    p.part_number,
                    p.part_number AS sku
                FROM purchase_order_items poi
                JOIN parts p ON p.part_id = poi.part_id
                WHERE poi.po_id = ANY(%s)
                ORDER BY poi.po_item_id ASC
            """
            all_items = conn.execute(items_query, (po_ids,)).fetchall()

            # Group items by po_id
            items_map: dict[int, list] = {oid: [] for oid in po_ids}
            for it in all_items:
                items_map[it["po_id"]].append(dict(it))

            return [_build_po_response(dict(o), items_map[o["po_id"]]) for o in orders]
    except Exception as e:
        logger.error(f"Error fetching purchase orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch purchase orders.")


@router.get("/purchase-orders/{id_or_number}", response_model=PurchaseOrderResponse)
def get_purchase_order(id_or_number: str):
    try:
        with get_db_connection() as conn:
            if id_or_number.isdigit():
                po = conn.execute(
                    """SELECT po.*, v.vendor_name 
                       FROM purchase_orders po 
                       LEFT JOIN vendors v ON v.vendor_id = po.vendor_id 
                       WHERE po.po_id = %s""",
                    (int(id_or_number),),
                ).fetchone()
            else:
                po = conn.execute(
                    """SELECT po.*, v.vendor_name 
                       FROM purchase_orders po 
                       LEFT JOIN vendors v ON v.vendor_id = po.vendor_id 
                       WHERE po.po_number = %s""",
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
                # 1. Resolve vendor_id
                vendor_id = payload.vendor_id or payload.supplier_id
                v_name_input = payload.vendor or payload.supplier
                if not vendor_id and v_name_input:
                    v_row = conn.execute(
                        "SELECT vendor_id FROM vendors WHERE LOWER(vendor_name) = LOWER(%s) OR LOWER(vendor_code) = LOWER(%s) LIMIT 1",
                        (v_name_input.strip(), v_name_input.strip()),
                    ).fetchone()
                    if v_row:
                        vendor_id = v_row["vendor_id"]

                # 2. Determine or generate PO Number
                po_num = payload.po_number
                if not po_num:
                    year = datetime.now().year
                    seq_row = conn.execute("SELECT COUNT(*) + 1 AS count FROM purchase_orders").fetchone()
                    seq = seq_row["count"] if seq_row else 1
                    po_num = f"PO-{year}-{seq:04d}"

                # 3. Assemble items: support multi-item list or legacy single-item payload
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

                # Calculate item line totals and sum total_order_value
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

                # 4. Insert PO record
                order_dt = payload.po_date or payload.order_date or datetime.now(timezone.utc)
                exp_dt = payload.expected_delivery_date or payload.expected_date

                po_record = conn.execute(
                    """INSERT INTO purchase_orders 
                       (po_number, vendor_id, po_date, expected_delivery_date, status, payment_terms, currency, total_order_value, created_by)
                       VALUES (%s, %s, %s, %s, 'Draft', %s, %s, %s, %s)
                       RETURNING *""",
                    (po_num, vendor_id, order_dt, exp_dt, payload.payment_terms or "Net 30", payload.currency or "INR", total_val, payload.created_by or "Procurement Officer"),
                ).fetchone()

                # 5. Insert line items
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

                    # Update stock_in_transit on inventory
                    conn.execute(
                        """UPDATE inventory 
                           SET stock_in_transit = COALESCE(stock_in_transit, 0) + %s,
                               last_updated = NOW()
                           WHERE part_id = %s""",
                        (it["ordered_quantity"], it["part_id"]),
                    )

                # 6. Fetch vendor name
                v_name = None
                if vendor_id:
                    v_row = conn.execute("SELECT vendor_name FROM vendors WHERE vendor_id = %s", (vendor_id,)).fetchone()
                    if v_row:
                        v_name = v_row["vendor_name"]

                po_dict = dict(po_record)
                po_dict["vendor_name"] = v_name
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

                return get_purchase_order(str(po["po_id"]))
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
    - Atomically update all items to received_quantity = ordered_quantity, pending_quantity = 0, item_status = 'Received'
    - Atomically increase inventory stock current_stock & available_stock for each part
    - Atomically adjust stock_in_transit
    - Atomically record inventory_transactions PO_RECEIPT audit record
    - Atomically update PO actual_delivery_date and status to 'Received'
    All executed within a single database transaction with row locks to prevent race conditions.
    """
    target_status = payload.status.capitalize()
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                where_clause = "po_id = %s" if id_or_number.isdigit() else "po_number = %s"
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
                    return get_purchase_order(str(po["po_id"]))

                if curr_status in ("Received", "Cancelled") and target_status in ("Received", "Draft"):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cannot change status of an already '{curr_status}' purchase order.",
                    )

                if target_status == "Received":
                    # Fetch all items for this PO with locks
                    items = conn.execute(
                        "SELECT * FROM purchase_order_items WHERE po_id = %s FOR UPDATE",
                        (po["po_id"],),
                    ).fetchall()

                    for item in items:
                        part_id = item["part_id"]
                        qty_ordered = item["ordered_quantity"]
                        qty_already_received = item.get("received_quantity", 0) or 0
                        qty_to_add = max(0, qty_ordered - qty_already_received)

                        if qty_to_add > 0:
                            # 1. Update inventory
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

                            # 2. Record inventory transaction audit record if table exists
                            try:
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
                            except Exception as tx_err:
                                logger.debug(f"Inventory transaction notice: {tx_err}")

                            # 3. Update received quantity and status on PO line
                            conn.execute(
                                """UPDATE purchase_order_items 
                                   SET received_quantity = ordered_quantity, 
                                       pending_quantity = 0, 
                                       item_status = 'Received' 
                                   WHERE po_item_id = %s""",
                                (item["po_item_id"],),
                            )

                    # 4. Mark PO received
                    conn.execute(
                        """UPDATE purchase_orders 
                           SET status = 'Received', actual_delivery_date = NOW()
                           WHERE po_id = %s""",
                        (po["po_id"],),
                    )
                else:
                    # Update status normally (e.g. Ordered, Draft, Cancelled)
                    conn.execute(
                        "UPDATE purchase_orders SET status = %s WHERE po_id = %s",
                        (target_status, po["po_id"]),
                    )

                return get_purchase_order(str(po["po_id"]))
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
                p.part_name,
                p.part_number,
                p.part_number AS sku
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
    except Exception as e:
        logger.error(f"Error fetching inventory transactions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch inventory transactions.")


@router.post("/inventory-transactions", response_model=InventoryTransactionResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def create_inventory_transaction(payload: InventoryTransactionCreate):
    try:
        with get_db_connection() as conn:
            with conn.transaction():
                # Verify part exists
                part = conn.execute("SELECT part_id, part_name, part_number FROM parts WHERE part_id = %s", (payload.part_id,)).fetchone()
                if not part:
                    raise HTTPException(status_code=404, detail="Part not found.")

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
                    """INSERT INTO inventory 
                       (part_id, current_stock, available_stock, reorder_point, safety_stock, maximum_stock, last_updated)
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
                p.part_number,
                p.part_number AS sku,
                p.part_name
            FROM demand_history dh
            JOIN parts p ON p.part_id = dh.part_id
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
        query += " ORDER BY dh.date DESC, p.part_name ASC LIMIT %s"
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
                part = conn.execute("SELECT part_id, part_number, part_name FROM parts WHERE part_id = %s", (payload.part_id,)).fetchone()
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
                item["part_number"] = part["part_number"]
                item["sku"] = part["part_number"]
                item["part_name"] = part["part_name"]
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
                p.part_number,
                p.part_number AS sku,
                p.part_name
            FROM forecasts f
            JOIN parts p ON p.part_id = f.part_id
            WHERE 1=1
        """
        params = []
        if part_id:
            query += " AND f.part_id = %s"
            params.append(part_id)
        if model_name:
            query += " AND LOWER(f.model_name) = LOWER(%s)"
            params.append(model_name)
        query += " ORDER BY f.forecast_date ASC, p.part_name ASC LIMIT %s"
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
                p.part_number,
                p.part_number AS sku,
                p.part_name,
                p.part_name AS part,
                p.category,
                latest_v.vendor_name AS primary_supplier
            FROM procurement_recommendations pr
            JOIN parts p ON p.part_id = pr.part_id
            LEFT JOIN LATERAL (
                SELECT v.vendor_name 
                FROM purchase_order_items poi
                JOIN purchase_orders po ON po.po_id = poi.po_id
                JOIN vendors v ON v.vendor_id = po.vendor_id
                WHERE poi.part_id = p.part_id
                ORDER BY po.po_date DESC NULLS LAST, po.po_id DESC
                LIMIT 1
            ) latest_v ON true
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
    reorder points, safety stocks, forecasted demand, and vendor lead times/pricing.
    PuLP consumes this single endpoint to produce cost-optimal order quantities.
    """
    try:
        with get_db_connection() as conn:
            query = """
                SELECT 
                    p.part_id,
                    p.part_number,
                    p.part_number AS sku,
                    p.part_name,
                    p.part_name AS name,
                    p.category,
                    COALESCE(p.criticality, 'Essential') AS criticality,
                    COALESCE(i.current_stock, 0) AS current_inventory,
                    COALESCE(i.reorder_point, p.reorder_point, 10) AS reorder_point,
                    COALESCE(i.safety_stock, p.safety_stock, 5) AS safety_stock,
                    COALESCE(i.maximum_stock, 50) AS max_stock,
                    COALESCE(latest_fc.forecast_quantity, 15.0) AS forecast_demand,
                    latest_po.vendor_id,
                    latest_po.vendor_id AS supplier_id,
                    v.vendor_name,
                    v.vendor_name AS supplier_name,
                    COALESCE(latest_po.unit_price, p.standard_cost, 0.0) AS supplier_unit_cost,
                    COALESCE(p.lead_time_days, v.default_lead_time_days, 7) AS lead_time_days,
                    COALESCE(p.minimum_order_quantity, 1) AS minimum_order_quantity
                FROM parts p
                LEFT JOIN inventory i ON i.part_id = p.part_id
                LEFT JOIN LATERAL (
                    SELECT forecast_quantity 
                    FROM forecasts f 
                    WHERE f.part_id = p.part_id 
                    ORDER BY forecast_date DESC 
                    LIMIT 1
                ) latest_fc ON true
                LEFT JOIN LATERAL (
                    SELECT po.vendor_id, poi.unit_price
                    FROM purchase_order_items poi
                    JOIN purchase_orders po ON po.po_id = poi.po_id
                    WHERE poi.part_id = p.part_id
                    ORDER BY po.po_date DESC NULLS LAST, po.po_id DESC
                    LIMIT 1
                ) latest_po ON true
                LEFT JOIN vendors v ON v.vendor_id = latest_po.vendor_id
                ORDER BY p.part_name ASC
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
    and vendor reliability metrics for prompt answering.
    """
    try:
        with get_db_connection() as conn:
            parts_count = conn.execute("SELECT COUNT(*) AS c FROM parts").fetchone()["c"]
            inv_stats = conn.execute(
                """SELECT 
                    COUNT(CASE WHEN COALESCE(i.current_stock, 0) <= COALESCE(i.safety_stock, p.safety_stock, 0) THEN 1 END) AS critical_count,
                    COUNT(CASE WHEN COALESCE(i.current_stock, 0) > COALESCE(i.safety_stock, p.safety_stock, 0) AND COALESCE(i.current_stock, 0) <= COALESCE(i.reorder_point, p.reorder_point, 0) THEN 1 END) AS warning_count,
                    COUNT(CASE WHEN COALESCE(i.current_stock, 0) > COALESCE(i.reorder_point, p.reorder_point, 0) THEN 1 END) AS healthy_count,
                    SUM(COALESCE(i.inventory_value, COALESCE(i.current_stock, 0) * COALESCE(p.standard_cost, 0))) AS total_inventory_value
                   FROM parts p
                   LEFT JOIN inventory i ON i.part_id = p.part_id"""
            ).fetchone()

            po_stats = conn.execute(
                """SELECT 
                    COUNT(*) AS total_pos,
                    COUNT(CASE WHEN LOWER(status) IN ('draft', 'ordered') THEN 1 END) AS open_pos,
                    COALESCE(SUM(CASE WHEN LOWER(status) IN ('draft', 'ordered') THEN total_order_value ELSE 0 END), 0) AS open_po_value
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
                    "critical_parts_count": inv_stats["critical_count"] if inv_stats else 0,
                    "warning_parts_count": inv_stats["warning_count"] if inv_stats else 0,
                    "healthy_parts_count": inv_stats["healthy_count"] if inv_stats else 0,
                    "total_inventory_value_inr": float((inv_stats and inv_stats["total_inventory_value"]) or 0),
                },
                "purchase_orders_summary": {
                    "total_orders": po_stats["total_pos"] if po_stats else 0,
                    "open_orders": po_stats["open_pos"] if po_stats else 0,
                    "open_orders_value_inr": float((po_stats and po_stats["open_po_value"]) or 0),
                },
                "procurement_optimization": {
                    "pending_recommendations_count": rec_stats["rec_count"] if rec_stats else 0,
                    "total_recommended_spend_inr": float((rec_stats and rec_stats["total_recommended_spend"]) or 0),
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
    Executes database seeding with authentic KSRTC parts, inventory, vendors,
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

@app.get("/vendors", include_in_schema=False)
@app.get("/suppliers", include_in_schema=False)
def root_vendors():
    return get_vendors()

@app.get("/purchase-orders", include_in_schema=False)
def root_purchase_orders():
    return get_purchase_orders()

@app.get("/procurement-recommendations", include_in_schema=False)
def root_procurement_recommendations():
    return get_procurement_recommendations()


# Include the API router
app.include_router(router)
