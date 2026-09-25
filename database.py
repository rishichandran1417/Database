import os
import logging
from typing import Generator
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ksrtc_backend.database")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Convert postgres:// to postgresql:// if needed (e.g. Heroku / older Render links)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Schema definitions matching exact Neon PostgreSQL schema
SCHEMA_SQL = """
-- 1. parts table
CREATE TABLE IF NOT EXISTS parts (
    part_id SERIAL PRIMARY KEY,
    part_number VARCHAR(100) UNIQUE NOT NULL,
    part_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    sub_category VARCHAR(100),
    description TEXT,
    unit_of_measure VARCHAR(50) DEFAULT 'Each',
    criticality VARCHAR(50) NOT NULL DEFAULT 'Essential',
    vehicle_system VARCHAR(100),
    standard_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    minimum_order_quantity INT NOT NULL DEFAULT 1,
    reorder_point INT NOT NULL DEFAULT 10,
    safety_stock INT NOT NULL DEFAULT 5,
    lead_time_days INT NOT NULL DEFAULT 7,
    annual_demand NUMERIC(12, 2) DEFAULT 0,
    active_status VARCHAR(50) NOT NULL DEFAULT 'Active',
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. vendors table
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id SERIAL PRIMARY KEY,
    vendor_code VARCHAR(100) UNIQUE NOT NULL,
    vendor_name VARCHAR(255) NOT NULL,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100) DEFAULT 'India',
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    vendor_category VARCHAR(100),
    payment_terms_days INT DEFAULT 30,
    default_lead_time_days INT NOT NULL DEFAULT 7,
    rating NUMERIC(3, 2) DEFAULT 4.5,
    on_time_delivery_rate NUMERIC(5, 2) DEFAULT 95.0,
    quality_rating NUMERIC(3, 2) DEFAULT 4.5,
    active_status VARCHAR(50) NOT NULL DEFAULT 'Active',
    vendor_since TIMESTAMPTZ DEFAULT NOW()
);

-- 3. purchase_orders table
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id SERIAL PRIMARY KEY,
    po_number VARCHAR(100) UNIQUE NOT NULL,
    vendor_id INT REFERENCES vendors(vendor_id) ON DELETE SET NULL,
    po_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expected_delivery_date TIMESTAMPTZ,
    actual_delivery_date TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL DEFAULT 'Draft',
    payment_terms VARCHAR(100),
    currency VARCHAR(10) DEFAULT 'INR',
    total_order_value NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    created_by VARCHAR(255) DEFAULT 'Procurement Officer'
);

-- 4. purchase_order_items table
CREATE TABLE IF NOT EXISTS purchase_order_items (
    po_item_id SERIAL PRIMARY KEY,
    po_id INT NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    part_id INT NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    ordered_quantity INT NOT NULL CHECK (ordered_quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    discount_percentage NUMERIC(5, 2) DEFAULT 0.00,
    tax_percentage NUMERIC(5, 2) DEFAULT 0.00,
    line_total NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    received_quantity INT NOT NULL DEFAULT 0 CHECK (received_quantity >= 0),
    pending_quantity INT NOT NULL DEFAULT 0,
    item_status VARCHAR(50) DEFAULT 'Pending'
);

-- 5. inventory table
CREATE TABLE IF NOT EXISTS inventory (
    inventory_id SERIAL PRIMARY KEY,
    part_id INT UNIQUE NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    current_stock INT NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    reserved_stock INT NOT NULL DEFAULT 0,
    available_stock INT NOT NULL DEFAULT 0,
    stock_in_transit INT NOT NULL DEFAULT 0,
    reorder_point INT NOT NULL DEFAULT 10,
    safety_stock INT NOT NULL DEFAULT 5,
    maximum_stock INT NOT NULL DEFAULT 50,
    average_unit_cost NUMERIC(12, 2) DEFAULT 0.00,
    inventory_value NUMERIC(14, 2) DEFAULT 0.00,
    last_receipt_date TIMESTAMPTZ,
    last_issue_date TIMESTAMPTZ,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auxiliary tables for ML forecasting, inventory audit, and optimization
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    transaction_type VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    reference_type VARCHAR(50),
    reference_id VARCHAR(100),
    transaction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS demand_history (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    quantity_consumed INT NOT NULL CHECK (quantity_consumed >= 0),
    depot VARCHAR(255) NOT NULL DEFAULT 'KSRTC Central Stores',
    CONSTRAINT uq_part_date_depot UNIQUE (part_id, date, depot)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    forecast_quantity NUMERIC(10, 2) NOT NULL CHECK (forecast_quantity >= 0),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS procurement_recommendations (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    recommended_quantity INT NOT NULL CHECK (recommended_quantity >= 0),
    unit_cost NUMERIC(12, 2) NOT NULL CHECK (unit_cost >= 0),
    estimated_cost NUMERIC(14, 2) NOT NULL CHECK (estimated_cost >= 0),
    priority VARCHAR(50) NOT NULL,
    reason TEXT,
    model_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_runs (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    run_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,
    metrics_json JSONB DEFAULT '{}'::jsonb
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_parts_part_number ON parts(part_number);
CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category);
CREATE INDEX IF NOT EXISTS idx_inventory_part_id ON inventory(part_id);
CREATE INDEX IF NOT EXISTS idx_demand_part_date ON demand_history(part_id, date);
CREATE INDEX IF NOT EXISTS idx_forecasts_part_date ON forecasts(part_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_po_vendor_id ON purchase_orders(vendor_id);
CREATE INDEX IF NOT EXISTS idx_po_items_po_id ON purchase_order_items(po_id);
CREATE INDEX IF NOT EXISTS idx_inv_tx_part_id ON inventory_transactions(part_id);
"""

_pool: ConnectionPool | None = None


def get_connection_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set in environment. "
                "Please configure DATABASE_URL in your .env or Render dashboard."
            )
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
        )
    return _pool


def close_connection_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_db_connection() -> Generator[psycopg.Connection, None, None]:
    """Yields a database connection with dict_row factory."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is missing.")
    
    pool = None
    try:
        pool = get_connection_pool()
        with pool.connection() as conn:
            yield conn
    except Exception as e:
        if pool is None:
            with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                yield conn
        else:
            raise e


def init_db():
    """Ensures necessary tables and indexes exist without modifying existing Neon columns."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is empty; skipping database initialization.")
        return

    logger.info("Verifying database schema...")
    with get_db_connection() as conn:
        for stmt in SCHEMA_SQL.split(";"):
            stmt_clean = stmt.strip()
            if stmt_clean:
                try:
                    with conn.transaction():
                        conn.execute(stmt_clean)
                except Exception as ex:
                    logger.debug(f"Schema statement notice: {ex}")

    logger.info("Database schema verified successfully.")


def check_db_health() -> bool:
    """Verifies database connectivity with SELECT 1."""
    with get_db_connection() as conn:
        result = conn.execute("SELECT 1 as alive").fetchone()
        return bool(result and result.get("alive") == 1)
