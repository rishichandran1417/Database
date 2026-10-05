"""
Unit tests for Inventory and Parts Catalog endpoints & models.
"""

from fastapi.testclient import TestClient
from main import app
from schemas.inventory import PartCreate, InventoryUpdate

client = TestClient(app)


def test_root_and_openapi():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    spec_response = client.get("/openapi.json")
    assert spec_response.status_code == 200
    paths = spec_response.json()["paths"]
    assert "/api/v1/db/parts" in paths
    assert "/api/v1/db/inventory" in paths


def test_part_model_validation():
    part = PartCreate(
        part_number="TEST-AIR-001",
        part_name="Test Heavy Duty Air Filter",
        category="Engine",
        standard_cost=1500.0,
        criticality="Critical",
        minimum_order_quantity=5,
        reorder_point=10,
        safety_stock=5,
    )
    assert part.part_number == "TEST-AIR-001"
    assert part.sku == "TEST-AIR-001"
    assert part.standard_cost == 1500.0
    assert part.unit_cost == 1500.0


def test_inventory_update_model():
    up = InventoryUpdate(current_stock=25, maximum_stock=100)
    assert up.current_stock == 25
    assert up.maximum_stock == 100
