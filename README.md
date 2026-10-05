# KSRTC Central Depot — Procurement & Supply Chain Backend API

Backend API and PostgreSQL central database service for the Kerala State Road Transport Corporation (**KSRTC**) spare parts procurement, inventory management, ML demand forecasting, and PuLP supply chain optimization platform.

> **Single Depot Architecture**: This application represents **KSRTC Central Stores**. Multi-depot logic is deliberately excluded per specification.

---

## 🏛️ System Architecture

This backend serves as the **SINGLE CENTRAL SOURCE OF TRUTH** for the entire platform:

```
database/
├── main.py
├── requirements.txt
├── .env
├── README.md
│
├── api/                        # HTTP / API route handlers
│   ├── __init__.py
│   ├── inventory.py
│   ├── purchase_orders.py
│   ├── suppliers.py
│   ├── forecasting.py
│   └── procurement.py
│
├── database/                   # Database connectivity, queries, & migrations ONLY
│   ├── __init__.py
│   ├── connection.py
│   ├── queries.py
│   └── migrations/
│
├── models/                     # Domain & schema re-exports
│   ├── __init__.py
│   ├── inventory.py
│   ├── purchase_order.py
│   ├── supplier.py
│   └── forecast.py
│
├── schemas/                    # Pydantic request / response schemas
│   ├── __init__.py
│   ├── inventory.py
│   ├── purchase_order.py
│   ├── forecast.py
│   └── procurement.py
│
├── services/                   # Business logic layer
│   ├── __init__.py
│   ├── inventory_service.py
│   ├── purchase_order_service.py
│   ├── forecasting_service.py
│   └── procurement_service.py
│
├── ml/                         # Machine Learning & PuLP Optimization
│   ├── __init__.py
│   ├── forecasting/            # XGBoost/LightGBM Demand Forecasting Pipeline
│   │   ├── __init__.py
│   │   ├── features.py         # Lag & rolling feature engineering
│   │   ├── train.py            # Time-based split model training
│   │   ├── predict.py          # Model loading & inference
│   │   ├── evaluation.py       # MAE, RMSE, MAPE metrics
│   │   └── models/             # Trained model storage (.joblib)
│   │
│   └── procurement/            # PuLP Mixed-Integer Linear Programming
│       ├── __init__.py
│       ├── optimize.py         # PuLP MILP solver engine
│       ├── constraints.py      # MOQ, max stock, safety stock constraints
│       ├── objective.py        # Cost minimization objective function
│       └── models/
│
├── utils/                      # Utilities & authentication
│   ├── __init__.py
│   ├── logging.py
│   └── validation.py
│
└── tests/                      # Automated validation suite
    ├── __init__.py
    ├── test_inventory.py
    ├── test_forecasting.py
    └── test_procurement.py
```

---

## 🤖 ML Demand Forecasting Pipeline

The system includes a time-series demand forecasting pipeline using **XGBoost**:

1. **Historical Data Source**: Extracted directly from `demand_history` table (`part_id`, `date`, `quantity_consumed`, `depot`).
2. **Feature Engineering** (`ml/forecasting/features.py`):
   - Lag features: `lag_1`, `lag_7`, `lag_14`, `lag_28`
   - Rolling statistics: `rolling_mean_7`, `rolling_mean_14`, `rolling_mean_28`, `rolling_std_28`
   - Calendar features: `day_of_week`, `day_of_month`, `month`, `quarter`, `year`
3. **Training & Evaluation** (`ml/forecasting/train.py`, `ml/forecasting/evaluation.py`):
   - Time-based train/validation split (chronological order, no random shuffle).
   - Evaluation metrics computed: `MAE`, `RMSE`, `MAPE`.
   - Model saved to `ml/forecasting/models/xgboost_demand_model.joblib`.
4. **Inference API** (`ml/forecasting/predict.py`, `GET /forecast/{part_id}`):
   - Loads trained model artifact (does NOT retrain on every request).
   - Generates 30-day forecast horizon structured as JSON:
     ```json
     {
       "part_id": "1",
       "model": "XGBoost",
       "forecast_horizon": 30,
       "forecast": [
         {"date": "2026-10-06", "forecast_quantity": 4.5}
       ],
       "total_forecast": 135.0,
       "mape": 12.5
     }
     ```

---

## 🧮 PuLP Procurement Optimization Engine

Workflow:
`Historical Demand` ➔ `ML Demand Forecast` ➔ `Inventory Requirements` ➔ `PuLP Optimization` ➔ `Recommended Procurement Quantity` ➔ `Purchase Order`

Supported Constraints (`ml/procurement/constraints.py`):
- Current stock vs Reorder Point & Safety Stock
- Minimum Order Quantity (MOQ)
- Maximum Order Quantity / Maximum Stock Level
- Vendor Lead Time & Pricing
- Total Budget Cap constraint (optional)

Endpoints:
- `GET /api/v1/db/procurement/optimization-input`
- `POST /api/v1/db/procurement/optimize`

---

## 🚀 Running the Application

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
Configure `.env`:
```env
DATABASE_URL=postgresql://username:password@hostname:5432/ksrtc_db
API_KEY=
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
PORT=8000
```

### 3. Run FastAPI Backend Server
```bash
uvicorn main:app --reload --port 8000
```

### 4. Run Test Suite
```bash
python test_app.py
# or
python -m pytest tests/
```

---

## 📦 Database Schema

| Table | Description |
|---|---|
| `parts` | Spare parts catalog with SKU, name, category, unit cost, and criticality. |
| `inventory` | Real-time stock levels, reorder points, safety stock, and maximum stock limits. |
| `vendors` | Registered vendors/suppliers with lead times and reliability ratings. |
| `purchase_orders` | Purchase orders with lifecycle tracking (`Draft` ➔ `Ordered` ➔ `Received` ➔ `Cancelled`). |
| `purchase_order_items` | Individual line items on purchase orders. |
| `inventory_transactions` | Immutable audit ledger for every stock change (`PO_RECEIPT`, `CONSUMPTION`, `ADJUSTMENT`). |
| `demand_history` | Historical daily consumption records for time-series modeling. |
| `forecasts` | Forecast records by part and date. |
| `procurement_recommendations` | Output from PuLP model with suggested order quantities and priorities. |
| `model_runs` | Audit log of ML and PuLP optimization model executions with metrics (MAE, RMSE, MAPE). |
