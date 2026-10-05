"""
Main FastAPI Application Entrypoint.
Restructured production architecture supporting FastAPI APIs, Neon PostgreSQL,
ML XGBoost Demand Forecasting, and PuLP Procurement Optimization.
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import check_db_health, close_connection_pool, get_db_connection, init_db
from schemas.inventory import HealthResponse
from utils.logging import logger
from utils.validation import verify_api_key

# Import API Routers from api/ package
from api.inventory import router as inventory_router
from api.purchase_orders import router as purchase_orders_router
from api.suppliers import router as suppliers_router
from api.forecasting import router as forecasting_router
from api.procurement import router as procurement_router

DEPOT_NAME = "KSRTC Central Stores"

# CORS configuration
ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]


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
    description="Central backend API & database source of truth for KSRTC spare-parts procurement, inventory, ML demand forecasting, and PuLP optimization.",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS Middleware
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
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "detail": "Internal server error occurred.", "error_type": type(exc).__name__},
    )


# Create master router with prefix /api/v1/db
main_router = APIRouter(prefix="/api/v1/db")


@main_router.get("/health", response_model=HealthResponse)
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


@main_router.get("/analytics/context")
def get_ai_analytics_context():
    """Unified context feed for AI Assistant and Dashboard Analytics."""
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


@main_router.post("/seed")
def trigger_database_seed():
    """Executes database seeding with authentic KSRTC supply chain data."""
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


# Include sub-routers into main_router
main_router.include_router(inventory_router)
main_router.include_router(purchase_orders_router)
main_router.include_router(suppliers_router)
main_router.include_router(forecasting_router)
main_router.include_router(procurement_router)

# Mount master router under /api/v1/db
app.include_router(main_router)


# Root level endpoints and backward-compatible aliases
@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "KSRTC Central Depot Procurement & Supply-Chain API",
        "docs_url": "/docs",
        "api_prefix": "/api/v1/db",
        "depot": DEPOT_NAME,
    }


@app.get("/health", response_model=HealthResponse)
def root_health():
    return health_check()


# Direct root endpoints for convenient frontend integration
from services.inventory_service import InventoryService
from services.purchase_order_service import PurchaseOrderService
from services.forecasting_service import ForecastingService
from services.procurement_service import ProcurementService


@app.get("/inventory", include_in_schema=False)
def root_inventory():
    return InventoryService.get_inventory()


@app.get("/parts", include_in_schema=False)
def root_parts():
    return InventoryService.get_parts()


@app.get("/vendors", include_in_schema=False)
@app.get("/suppliers", include_in_schema=False)
def root_vendors():
    from api.suppliers import get_vendors
    return get_vendors()


@app.get("/purchase-orders", include_in_schema=False)
def root_purchase_orders():
    return PurchaseOrderService.get_purchase_orders()


@app.get("/procurement-recommendations", include_in_schema=False)
def root_procurement_recommendations():
    return ProcurementService.get_recommendations()


@app.get("/forecast", response_model=None, include_in_schema=False)
def root_forecast_probe():
    return ForecastingService.get_ml_service_health()


@app.post("/forecast/predict", include_in_schema=False)
def root_forecast_predict(payload: dict):
    part_id = int(payload.get("part_id", 1))
    horizon = int(payload.get("forecast_horizon", 30))
    return ForecastingService.generate_part_forecast(part_id, horizon)


@app.get("/forecast/{part_id}", include_in_schema=False)
@app.post("/forecast/{part_id}", include_in_schema=False)
def root_forecast_part(part_id: int, forecast_horizon: int = 30):
    return ForecastingService.generate_part_forecast(part_id, forecast_horizon=forecast_horizon)





@app.post("/procurement/optimize", include_in_schema=False)
@app.get("/procurement/optimize", include_in_schema=False)
def root_procurement_optimize():
    return ProcurementService.optimize_procurement()
