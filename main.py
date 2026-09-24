import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal, Optional

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg import errors
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

# ---------- Config (set these as environment variables) ----------
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.getenv("API_KEY")  # optional: if set, writes need X-API-Key header
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

SCHEMA = """
CREATE TABLE IF NOT EXISTS parts (
    id          SERIAL PRIMARY KEY,
    sku         TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    category    TEXT,
    unit_cost   NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory (
    part_id        INT PRIMARY KEY REFERENCES parts(id) ON DELETE CASCADE,
    quantity       INT NOT NULL DEFAULT 0,
    reorder_point  INT NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id             SERIAL PRIMARY KEY,
    part_id        INT NOT NULL REFERENCES parts(id),
    supplier       TEXT,
    quantity       INT NOT NULL CHECK (quantity > 0),
    unit_cost      NUMERIC(12,2),
    status         TEXT NOT NULL DEFAULT 'draft',
    expected_date  DATE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    received_at    TIMESTAMPTZ
);
"""


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with db() as conn:  # creates tables on first start
        conn.execute(SCHEMA)
    yield


app = FastAPI(title="Procurement API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------- Models ----------
class PartIn(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    unit_cost: float = Field(0, ge=0)


class StockIn(BaseModel):
    quantity: int = Field(ge=0)
    reorder_point: int = Field(0, ge=0)


class PurchaseOrderIn(BaseModel):
    part_id: int
    supplier: Optional[str] = None
    quantity: int = Field(gt=0)
    unit_cost: Optional[float] = Field(None, ge=0)
    expected_date: Optional[date] = None


class StatusIn(BaseModel):
    status: Literal["draft", "ordered", "shipped", "received", "cancelled"]


# ---------- Routes ----------
router = APIRouter(prefix="/api/v1/db")


@router.get("/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


# Parts catalog
@router.get("/parts")
def list_parts():
    with db() as conn:
        return conn.execute("SELECT * FROM parts ORDER BY name").fetchall()


@router.post("/parts", status_code=201, dependencies=[Depends(require_key)])
def add_part(part: PartIn):
    try:
        with db() as conn:
            return conn.execute(
                """INSERT INTO parts (sku, name, category, unit_cost)
                   VALUES (%s, %s, %s, %s) RETURNING *""",
                (part.sku, part.name, part.category, part.unit_cost),
            ).fetchone()
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="SKU already exists")


# Inventory stock levels
@router.get("/inventory")
def list_inventory():
    try:
        with db() as conn:
            return conn.execute(
                """SELECT p.id AS part_id,
                          p.sku,
                          p.name,
                          COALESCE(i.quantity, 0) AS quantity,
                          COALESCE(i.reorder_point, 0) AS reorder_point,
                          i.updated_at
                   FROM parts p
                   LEFT JOIN inventory i ON i.part_id = p.id
                   ORDER BY p.name"""
            ).fetchall()

    except Exception as e:
        print(f"INVENTORY ERROR: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {str(e)}"
        )


@router.put("/inventory/{part_id}", dependencies=[Depends(require_key)])
def set_stock(part_id: int, stock: StockIn):
    try:
        with db() as conn:
            return conn.execute(
                """INSERT INTO inventory (part_id, quantity, reorder_point)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (part_id) DO UPDATE
                   SET quantity = EXCLUDED.quantity,
                       reorder_point = EXCLUDED.reorder_point,
                       updated_at = now()
                   RETURNING *""",
                (part_id, stock.quantity, stock.reorder_point),
            ).fetchone()
    except errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="Part not found")


# Purchase orders
@router.get("/purchase-orders")
def list_purchase_orders(status: Optional[str] = None):
    with db() as conn:
        if status:
            return conn.execute(
                "SELECT * FROM purchase_orders WHERE status = %s ORDER BY id DESC",
                (status,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM purchase_orders ORDER BY id DESC"
        ).fetchall()


@router.post("/purchase-orders", status_code=201, dependencies=[Depends(require_key)])
def create_purchase_order(po: PurchaseOrderIn):
    try:
        with db() as conn:
            return conn.execute(
                """INSERT INTO purchase_orders
                       (part_id, supplier, quantity, unit_cost, expected_date)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (po.part_id, po.supplier, po.quantity, po.unit_cost, po.expected_date),
            ).fetchone()
    except errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="Part not found")


@router.patch("/purchase-orders/{po_id}/status", dependencies=[Depends(require_key)])
def update_po_status(po_id: int, body: StatusIn):
    with db() as conn:
        po = conn.execute(
            "SELECT * FROM purchase_orders WHERE id = %s FOR UPDATE", (po_id,)
        ).fetchone()
        if not po:
            raise HTTPException(status_code=404, detail="Purchase order not found")
        if po["status"] in ("received", "cancelled"):
            raise HTTPException(status_code=409, detail=f"Order already {po['status']}")

        if body.status == "received":
            # Receiving an order adds its quantity to stock
            conn.execute(
                """INSERT INTO inventory (part_id, quantity)
                   VALUES (%s, %s)
                   ON CONFLICT (part_id) DO UPDATE
                   SET quantity = inventory.quantity + EXCLUDED.quantity,
                       updated_at = now()""",
                (po["part_id"], po["quantity"]),
            )
            return conn.execute(
                """UPDATE purchase_orders
                   SET status = 'received', received_at = now()
                   WHERE id = %s RETURNING *""",
                (po_id,),
            ).fetchone()

        return conn.execute(
            "UPDATE purchase_orders SET status = %s WHERE id = %s RETURNING *",
            (body.status, po_id),
        ).fetchone()


app.include_router(router)


@app.get("/")
def root():
    return {"status": "ok"}
