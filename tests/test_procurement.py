"""
Unit tests for PuLP Procurement Optimization engine and API endpoints.
"""

from fastapi.testclient import TestClient
from main import app
from ml.procurement.optimize import run_procurement_optimization

client = TestClient(app)


def test_pulp_optimization_engine():
    mock_input = [
        {
            "part_id": 1,
            "part_number": "ENG-AL-001",
            "part_name": "Engine Oil Filter Spin-On",
            "category": "Engine",
            "criticality": "Critical",
            "current_inventory": 5,  # below safety stock of 15
            "safety_stock": 15,
            "reorder_point": 30,
            "max_stock": 80,
            "forecast_demand": 25.0,
            "supplier_unit_cost": 850.0,
            "supplier_id": 1,
            "supplier_name": "Ashok Leyland Spares",
            "lead_time_days": 7,
            "minimum_order_quantity": 10,
        },
        {
            "part_id": 2,
            "part_number": "BRK-AL-001",
            "part_name": "Brake Lining Set",
            "category": "Braking System",
            "criticality": "Critical",
            "current_inventory": 50,  # healthy inventory
            "safety_stock": 25,
            "reorder_point": 45,
            "max_stock": 120,
            "forecast_demand": 10.0,
            "supplier_unit_cost": 4500.0,
            "supplier_id": 2,
            "supplier_name": "TVS Brake Linings",
            "lead_time_days": 5,
            "minimum_order_quantity": 5,
        },
    ]

    res = run_procurement_optimization(mock_input)
    assert res["status"] in ("optimal", "evaluated")
    assert "PuLP" in res["optimization_engine"]
    assert res["total_parts_analyzed"] == 2
    assert res["total_parts_to_order"] >= 1

    # Eng filter is critical & below safety stock -> must be recommended for order
    recs = {r["part_id"]: r for r in res["recommendations"]}
    assert 1 in recs
    assert recs[1]["recommended_order_quantity"] >= 10  # MOQ constraint
    assert recs[1]["priority"] == "Critical"


def test_procurement_optimization_endpoints():
    res = client.get("/api/v1/db/procurement/optimization-input")
    assert res.status_code == 200
    data = res.json()
    assert "depot" in data
    assert "items" in data

    res_opt = client.post("/api/v1/db/procurement/optimize")
    assert res_opt.status_code == 200
    opt_data = res_opt.json()
    assert "optimization_engine" in opt_data
    assert "recommendations" in opt_data
