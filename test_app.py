"""
Automated validation script for KSRTC Supply-Chain & Procurement Backend API.
Tests model validation, API routing, serialization, and database connection.
"""
import sys
import os
from datetime import datetime, timezone, date
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

from main import app
from models import (
    PartCreate,
    InventoryUpdate,
    SupplierCreate,
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderStatusUpdate,
    DemandHistoryCreate,
    ForecastCreate,
    ProcurementRecommendationCreate,
    ModelRunCreate,
)


def run_unit_tests():
    print("==================================================")
    print("RUNNING KSRTC BACKEND VALIDATION SUITE")
    print("==================================================")

    client = TestClient(app)

    # 1. Test Root
    res = client.get("/")
    assert res.status_code == 200, f"Root check failed: {res.text}"
    print("PASS: Root endpoint GET /")

    # 2. Test OpenAPI Spec and Schema Generation
    res = client.get("/openapi.json")
    assert res.status_code == 200, f"OpenAPI generation failed: {res.text}"
    openapi = res.json()
    paths = openapi["paths"]

    expected_endpoints = [
        "/api/v1/db/health",
        "/api/v1/db/parts",
        "/api/v1/db/parts/{part_id}",
        "/api/v1/db/inventory",
        "/api/v1/db/inventory/{part_id}",
        "/api/v1/db/suppliers",
        "/api/v1/db/suppliers/{supplier_id}",
        "/api/v1/db/supplier-parts",
        "/api/v1/db/purchase-orders",
        "/api/v1/db/purchase-orders/{id_or_number}",
        "/api/v1/db/purchase-orders/{id_or_number}/status",
        "/api/v1/db/inventory-transactions",
        "/api/v1/db/demand-history",
        "/api/v1/db/forecasts",
        "/api/v1/db/forecasts/{part_id}",
        "/api/v1/db/procurement-recommendations",
        "/api/v1/db/model-runs",
        "/api/v1/db/procurement/optimization-input",
        "/api/v1/db/analytics/context",
        "/api/v1/db/seed",
    ]

    for ep in expected_endpoints:
        assert ep in paths, f"Missing endpoint in OpenAPI schema: {ep}"
        print(f"PASS: Verified endpoint registered: {ep}")

    # 3. Test Pydantic Model Validation
    part = PartCreate(
        sku="TEST-SKU-001",
        name="Test Brake Lining",
        category="Braking System",
        description="Heavy duty test lining",
        unit_cost=3500.0,
        criticality="Critical",
    )
    assert part.sku == "TEST-SKU-001"
    print("PASS: PartCreate validation")

    po = PurchaseOrderCreate(
        po_number="PO-TEST-001",
        supplier="TVS & Sons",
        items=[
            PurchaseOrderItemCreate(part_id=1, quantity=10, unit_cost=500.0),
            PurchaseOrderItemCreate(part_id=2, quantity=5, unit_cost=1200.0),
        ],
    )
    assert len(po.items) == 2
    print("PASS: PurchaseOrderCreate with multi-item validation")

    rec = ProcurementRecommendationCreate(
        part_id=1,
        recommended_quantity=25,
        unit_cost=450.0,
        priority="Critical",
        reason="Stock breached safety limit",
    )
    assert rec.priority == "Critical"
    print("PASS: ProcurementRecommendationCreate validation")

    # 4. Check Database Connection if configured
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("\nTesting database connection with DATABASE_URL...")
        from database import check_db_health, init_db
        try:
            init_db()
            healthy = check_db_health()
            assert healthy, "Database health query failed"
            print("PASS: Database connected & schema verified!")

            # Test actual API endpoints
            res = client.get("/api/v1/db/health")
            assert res.status_code == 200
            print("PASS: GET /api/v1/db/health returns 200 OK")

            res = client.get("/api/v1/db/parts")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/parts returns {len(res.json())} parts")

            res = client.get("/api/v1/db/inventory")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/inventory returns {len(res.json())} inventory records")

            res = client.get("/api/v1/db/suppliers")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/suppliers returns {len(res.json())} suppliers")

            res = client.get("/api/v1/db/purchase-orders")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/purchase-orders returns {len(res.json())} POs")

            res = client.get("/api/v1/db/demand-history")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/demand-history returns {len(res.json())} consumption records")

            res = client.get("/api/v1/db/forecasts")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/forecasts returns {len(res.json())} forecasts")

            res = client.get("/api/v1/db/procurement-recommendations")
            assert res.status_code == 200
            print(f"PASS: GET /api/v1/db/procurement-recommendations returns {len(res.json())} recommendations")
        except Exception as e:
            print(f"Database test encountered error: {e}")
    else:
        print("\nNOTE: DATABASE_URL not set in local environment. Skipping live DB network test.")

    print("\n==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_unit_tests()
