# KSRTC Central Depot — Procurement & Supply Chain Backend API

Backend API and PostgreSQL central database service for the Kerala State Road Transport Corporation (**KSRTC**) spare parts procurement, inventory management, demand forecasting, and supply chain analytics platform.

> **Single Depot Architecture**: This application represents **KSRTC Central Stores**. Multi-depot logic is deliberately excluded per specification.

---

## 🏛️ System Architecture

This backend serves as the **SINGLE CENTRAL SOURCE OF TRUTH** for the entire platform:

```
                      ┌────────────────────────────────────────┐
                      │ PostgreSQL Database (Render / Cloud)   │
                      │  - parts           - purchase_orders   │
                      │  - inventory       - inventory_tx      │
                      │  - suppliers       - demand_history    │
                      │  - supplier_parts  - forecasts         │
                      │  - recommendations - model_runs        │
                      └───────────────────▲────────────────────┘
                                          │
                                          │ psycopg 3 connection pool
                                          │
                      ┌───────────────────▼────────────────────┐
                      │ FastAPI Backend API (Render)           │
                      │ Base URL: https://database-5oe4.onrender.com
                      │ Prefix:   /api/v1/db                   │
                      └─┬──────────────┬────────────┬────────┬─┘
                        │              │            │        │
         ┌──────────────┘              │            │        └──────────────┐
         ▼                             ▼            ▼                       ▼
┌──────────────────┐          ┌─────────────┐ ┌───────────────┐   ┌───────────────────┐
│ React Frontend   │          │ XGBoost ML  │ │ PuLP Optimizer│   │ Gemini AI Assistant│
│ - Inventory      │          │ Forecasting │ │ - Procurement │   │ - Budget & stock  │
│ - Purchase Orders│          │ - Reads     │ │   allocations │   │   recommendations │
│ - Suppliers View │          │   history   │ │ - Reads MOQ/  │   │ - Natural language│
│ - Live Stock     │          │ - Posts fc  │ │   prices/stock│   │   queries         │
└──────────────────┘          └─────────────┘ └───────────────┘   └───────────────────┘
```

---

## 📦 Database Schema

The database consists of 11 relational tables managed through `psycopg 3` with automatic idempotent schema migrations:

| Table | Description |
|---|---|
| `parts` | Spare parts catalog with SKU, name, category, unit cost, and criticality. |
| `inventory` | Real-time stock levels, reorder points, safety stock, and maximum stock limits. |
| `suppliers` | Registered suppliers and vendors with lead times and reliability ratings. |
| `supplier_parts` | Vendor-specific catalog with negotiated unit costs, lead times, and MOQs. |
| `purchase_orders` | Purchase orders with lifecycle tracking (`Draft` ➔ `Ordered` ➔ `Received` ➔ `Cancelled`). |
| `purchase_order_items` | Individual line items on purchase orders. |
| `inventory_transactions` | Complete immutable audit ledger for every stock change (`PO_RECEIPT`, `CONSUMPTION`, `ADJUSTMENT`). |
| `demand_history` | Historical daily consumption records for time-series modeling and XGBoost. |
| `forecasts` | ML model forecasts by part and forecast date. |
| `procurement_recommendations` | Output from PuLP linear programming model with suggested order quantities and priorities. |
| `model_runs` | Audit log of ML and PuLP optimization model executions with metrics (MAE, RMSE, MAPE). |

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.10 – 3.14)
- PostgreSQL database instance (local or hosted on Render, Supabase, Neon, AWS RDS, etc.)

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/rishichandran1417/Database.git
cd Database
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file from the provided template:
```bash
cp .env.example .env
```

Configure your variables in `.env`:
```env
# PostgreSQL connection string (Never commit real credentials)
DATABASE_URL=postgresql://postgres:password@localhost:5432/ksrtc_db

# Optional write-endpoint security key
API_KEY=your_secure_api_key_here

# Allowed origins for CORS (comma-separated)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,https://my-frontend.vercel.app
```

---

## 🏃 Running the Application

### 1. Start the FastAPI Dev Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive Swagger UI: `http://localhost:8000/docs`
- ReDoc Documentation: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/api/v1/db/health`

### 2. Populate Database with Seed Data
Run the idempotent seed script to populate realistic KSRTC parts (Ashok Leyland spares), suppliers (TVS, Brakes India, Lucas-TVS, MRF), 90 days of daily consumption history, and sample POs:
```bash
python seed.py
```
*Note: `seed.py` is safe to run multiple times without creating duplicates.*

Alternatively, trigger seeding via the API:
```bash
curl -X POST http://localhost:8000/api/v1/db/seed
```

---

## 🌐 Render Deployment

1. **Connect Repository**: Link `https://github.com/rishichandran1417/Database` to Render.
2. **Environment**: Select **Python 3**.
3. **Build Command**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Start Command**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
5. **Environment Variables**:
   - `DATABASE_URL`: Your Render PostgreSQL database connection string (internal or external).
   - `ALLOWED_ORIGINS`: Your React frontend domain (e.g. `https://ksrtc-procurement.vercel.app`).
   - `API_KEY`: (Optional) Secret key to secure write operations.

---

## 📖 API Endpoints Reference

All endpoints are prefixed with `/api/v1/db`:

### Health & Analytics
- `GET /api/v1/db/health` — PostgreSQL connection health check.
- `GET /api/v1/db/analytics/context` — Depot KPIs and summary context for Gemini AI Assistant.
- `GET /api/v1/db/procurement/optimization-input` — Unified input feed for PuLP optimization model.
- `POST /api/v1/db/seed` — Trigger idempotent database seed.

### Parts (`/api/v1/db/parts`)
- `GET /parts` — List all spare parts (supports `?category=`, `?criticality=`, `?search=`).
- `GET /parts/{id}` — Get single part details.
- `POST /parts` — Create a new spare part. *(Requires X-API-Key if enabled)*
- `PUT /parts/{id}` — Update part details. *(Requires X-API-Key if enabled)*
- `DELETE /parts/{id}` — Delete part. *(Requires X-API-Key if enabled)*

### Inventory (`/api/v1/db/inventory`)
- `GET /inventory` — List all stock levels with status (`Healthy`, `Warning`, `Critical`) and stockout risk.
- `GET /inventory/{part_id}` — Get stock levels for a specific part.
- `PUT /inventory/{part_id}` — Update stock quantity, reorder point, or safety stock.

### Suppliers (`/api/v1/db/suppliers`)
- `GET /suppliers` — List all suppliers (supports `?status=`, `?category=`).
- `GET /suppliers/{id}` — Get single supplier.
- `POST /suppliers` — Register a new supplier.
- `PUT /suppliers/{id}` — Update supplier information.
- `DELETE /suppliers/{id}` — Delete supplier.

### Supplier Parts (`/api/v1/db/supplier-parts`)
- `GET /supplier-parts` — List supplier-part price quotes, lead times, and MOQs.
- `POST /supplier-parts` — Link part to supplier with unit cost, lead time, and MOQ.

### Purchase Orders (`/api/v1/db/purchase-orders`)
- `GET /purchase-orders` — List purchase orders (supports `?status=Ordered`, etc.).
- `GET /purchase-orders/{id}` — Get purchase order with line items.
- `POST /purchase-orders` — Create new purchase order with multi-item lines.
- `PUT /purchase-orders/{id}` — Update purchase order metadata.
- `PATCH /purchase-orders/{id}/status` — **Key business logic**: Updating status to `"received"` atomically updates inventory quantity, creates audit ledger transactions, and marks order received.

### Demand History (`/api/v1/db/demand-history`)
- `GET /demand-history` — Retrieve historical consumption data (supports `?part_id=`, `?start_date=`, `?end_date=`).
- `POST /demand-history` — Record single daily consumption entry.
- `POST /demand-history/batch` — Bulk import consumption entries for model training.

### Forecasts (`/api/v1/db/forecasts`)
- `GET /forecasts` — Get ML forecasts (supports `?part_id=`, `?model_name=`).
- `GET /forecasts/{part_id}` — Get forecasts for a specific part.
- `POST /forecasts` — Store ML model forecasts (supports batch upload).

### Procurement Recommendations (`/api/v1/db/procurement-recommendations`)
- `GET /procurement-recommendations` — List optimization recommendations by priority.
- `POST /procurement-recommendations` — Store PuLP procurement outputs (supports batch upload).

### Model Runs (`/api/v1/db/model-runs`)
- `GET /model-runs` — View execution history of forecasting & optimization models.
- `POST /model-runs` — Record a model execution run with metrics JSON.

---

## 🔒 Security & CORS

- **CORS**: Configured dynamically via `ALLOWED_ORIGINS`. Localhost is permitted during local development.
- **API Protection**: Read endpoints (`GET`) remain publicly accessible for client displays and model querying. Write operations (`POST`, `PUT`, `PATCH`, `DELETE`) are protected by the `X-API-Key` header when `API_KEY` is configured in the environment.
- **Database Safety**: Database credentials are strictly read from `DATABASE_URL` and never exposed in API responses or frontend client code.
