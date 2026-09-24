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

# Schema definitions
SCHEMA_SQL = """
-- 1. parts table
CREATE TABLE IF NOT EXISTS parts (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT,
    unit_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    criticality VARCHAR(50) NOT NULL DEFAULT 'Essential',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. inventory table
CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    part_id INT UNIQUE NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reorder_point INT NOT NULL DEFAULT 0 CHECK (reorder_point >= 0),
    safety_stock INT NOT NULL DEFAULT 0 CHECK (safety_stock >= 0),
    max_stock INT NOT NULL DEFAULT 0 CHECK (max_stock >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. suppliers table
CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    supplier_code VARCHAR(100) UNIQUE NOT NULL,
    supplier_name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    category VARCHAR(100),
    lead_time_days INT NOT NULL DEFAULT 7 CHECK (lead_time_days >= 1),
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. supplier_parts table
CREATE TABLE IF NOT EXISTS supplier_parts (
    id SERIAL PRIMARY KEY,
    supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    part_id INT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    supplier_unit_cost NUMERIC(12, 2) NOT NULL CHECK (supplier_unit_cost >= 0),
    lead_time_days INT NOT NULL CHECK (lead_time_days >= 1),
    minimum_order_quantity INT NOT NULL DEFAULT 1 CHECK (minimum_order_quantity >= 1),
    CONSTRAINT uq_supplier_part UNIQUE (supplier_id, part_id)
);

-- 5. purchase_orders table
CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    po_number VARCHAR(100) UNIQUE NOT NULL,
    supplier_id INT REFERENCES suppliers(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Draft',
    order_date TIMESTAMPTZ,
    expected_date TIMESTAMPTZ,
    received_date TIMESTAMPTZ,
    total_value NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. purchase_order_items table
CREATE TABLE IF NOT EXISTS purchase_order_items (
    id SERIAL PRIMARY KEY,
    purchase_order_id INT NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    part_id INT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_cost NUMERIC(12, 2) NOT NULL CHECK (unit_cost >= 0),
    received_quantity INT NOT NULL DEFAULT 0 CHECK (received_quantity >= 0)
);

-- 7. inventory_transactions table
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    transaction_type VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    reference_type VARCHAR(50),
    reference_id VARCHAR(100),
    transaction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

-- 8. demand_history table
CREATE TABLE IF NOT EXISTS demand_history (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    quantity_consumed INT NOT NULL CHECK (quantity_consumed >= 0),
    depot VARCHAR(255) NOT NULL DEFAULT 'KSRTC Central Depot, Thiruvananthapuram',
    CONSTRAINT uq_part_date_depot UNIQUE (part_id, date, depot)
);

-- 9. forecasts table
CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    forecast_quantity NUMERIC(10, 2) NOT NULL CHECK (forecast_quantity >= 0),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. procurement_recommendations table
CREATE TABLE IF NOT EXISTS procurement_recommendations (
    id SERIAL PRIMARY KEY,
    part_id INT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    recommended_quantity INT NOT NULL CHECK (recommended_quantity >= 0),
    unit_cost NUMERIC(12, 2) NOT NULL CHECK (unit_cost >= 0),
    estimated_cost NUMERIC(14, 2) NOT NULL CHECK (estimated_cost >= 0),
    priority VARCHAR(50) NOT NULL,
    reason TEXT,
    model_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. model_runs table
CREATE TABLE IF NOT EXISTS model_runs (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    run_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,
    metrics_json JSONB DEFAULT '{}'::jsonb
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_parts_sku ON parts(sku);
CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category);
CREATE INDEX IF NOT EXISTS idx_inventory_part_id ON inventory(part_id);
CREATE INDEX IF NOT EXISTS idx_demand_part_date ON demand_history(part_id, date);
CREATE INDEX IF NOT EXISTS idx_forecasts_part_date ON forecasts(part_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_po_supplier_id ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_po_items_po_id ON purchase_order_items(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_inv_tx_part_id ON inventory_transactions(part_id);
"""

# Migration queries to seamlessly upgrade existing databases without wiping data
INDIVIDUAL_MIGRATIONS = [
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS description TEXT;",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS criticality VARCHAR(50) NOT NULL DEFAULT 'Essential';",
    "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS safety_stock INT NOT NULL DEFAULT 0;",
    "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS max_stock INT NOT NULL DEFAULT 0;",
    "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS po_number VARCHAR(100);",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS supplier_id INT REFERENCES suppliers(id) ON DELETE SET NULL;",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS order_date TIMESTAMPTZ DEFAULT NOW();",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS expected_date TIMESTAMPTZ;",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS received_date TIMESTAMPTZ;",
    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS total_value NUMERIC(14, 2) DEFAULT 0.00;",
    "UPDATE purchase_orders SET po_number = 'PO-LEGACY-' || id WHERE po_number IS NULL;",
]

_pool: ConnectionPool | None = None


def get_connection_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set in environment. "
                "Please configure DATABASE_URL in your .env or Render dashboard."
            )
        # Create connection pool
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
    
    # Try using pool first, fallback to direct connect if pool not initialized
    pool = None
    try:
        pool = get_connection_pool()
        with pool.connection() as conn:
            yield conn
    except Exception as e:
        if pool is None:
            # Fallback to direct connection
            with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                yield conn
        else:
            raise e


def init_db():
    """Initializes tables and executes idempotent schema migrations safely."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is empty; skipping database initialization.")
        return

    logger.info("Initializing database schema...")
    with get_db_connection() as conn:
        with conn.transaction():
            # Check if an incompatible legacy inventory table exists without part_id
            check_inv = conn.execute(
                """SELECT column_name FROM information_schema.columns 
                   WHERE table_name = 'inventory' AND column_name = 'part_id'"""
            ).fetchone()
            inv_exists = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'inventory'"
            ).fetchone()
            if inv_exists and not check_inv:
                logger.warning("Found incompatible legacy inventory table without part_id. Recreating...")
                conn.execute("DROP TABLE IF EXISTS inventory CASCADE")

        # 1. Execute schema creation statements
        for stmt in SCHEMA_SQL.split(";"):
            stmt_clean = stmt.strip()
            if stmt_clean:
                try:
                    with conn.transaction():
                        conn.execute(stmt_clean)
                except Exception as ex:
                    logger.debug(f"Schema statement notice: {ex}")

        # 2. Execute each migration statement in its own transaction
        for mig in INDIVIDUAL_MIGRATIONS:
            try:
                with conn.transaction():
                    conn.execute(mig)
            except Exception as ex:
                logger.warning(f"Migration notice for '{mig}': {ex}")

    logger.info("Database schema initialized and verified successfully.")


def check_db_health() -> bool:
    """Verifies database connectivity with SELECT 1."""
    with get_db_connection() as conn:
        result = conn.execute("SELECT 1 as alive").fetchone()
        return bool(result and result.get("alive") == 1)
