from api.inventory import router as inventory_router
from api.purchase_orders import router as purchase_orders_router
from api.suppliers import router as suppliers_router
from api.forecasting import router as forecasting_router
from api.procurement import router as procurement_router

__all__ = [
    "inventory_router",
    "purchase_orders_router",
    "suppliers_router",
    "forecasting_router",
    "procurement_router",
]
