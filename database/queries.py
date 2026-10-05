"""
Central repository of SQL queries for database data access.
The database package is strictly restricted to connection management, SQL queries, and migrations.
"""

# Parts Queries
SELECT_ALL_PARTS = """
    SELECT 
        part_id, part_number, part_name, category, sub_category,
        description, unit_of_measure, criticality, vehicle_system,
        standard_cost, minimum_order_quantity, reorder_point,
        safety_stock, lead_time_days, annual_demand, active_status,
        created_date
    FROM parts 
    WHERE 1=1
"""

SELECT_PART_BY_ID = "SELECT * FROM parts WHERE part_id = %s"

INSERT_PART = """
    INSERT INTO parts 
    (part_number, part_name, category, sub_category, description, 
     unit_of_measure, criticality, vehicle_system, standard_cost, 
     minimum_order_quantity, reorder_point, safety_stock, 
     lead_time_days, annual_demand, active_status, created_date)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    RETURNING *
"""

DELETE_PART = "DELETE FROM parts WHERE part_id = %s RETURNING part_id"

# Inventory Queries
SELECT_ALL_INVENTORY = """
    SELECT 
        COALESCE(i.inventory_id, p.part_id) AS id,
        i.inventory_id,
        p.part_id,
        p.part_number,
        p.part_number AS sku,
        p.part_name,
        p.part_name AS name,
        p.part_name AS part,
        p.category,
        p.sub_category,
        COALESCE(p.criticality, 'Essential') AS criticality,
        COALESCE(p.standard_cost, 0.0) AS standard_cost,
        COALESCE(p.standard_cost, 0.0) AS unit_cost,
        COALESCE(i.average_unit_cost, p.standard_cost, 0.0) AS average_unit_cost,
        COALESCE(i.current_stock, 0) AS current_stock,
        COALESCE(i.current_stock, 0) AS quantity,
        COALESCE(i.current_stock, 0) AS "currentStock",
        COALESCE(i.reserved_stock, 0) AS reserved_stock,
        COALESCE(i.available_stock, COALESCE(i.current_stock, 0) - COALESCE(i.reserved_stock, 0)) AS available_stock,
        COALESCE(i.stock_in_transit, 0) AS stock_in_transit,
        COALESCE(i.reorder_point, p.reorder_point, 10) AS reorder_point,
        COALESCE(i.reorder_point, p.reorder_point, 10) AS "reorderPoint",
        COALESCE(i.safety_stock, p.safety_stock, 5) AS safety_stock,
        COALESCE(i.safety_stock, p.safety_stock, 5) AS "safetyStock",
        COALESCE(i.maximum_stock, 50) AS maximum_stock,
        COALESCE(i.maximum_stock, 50) AS max_stock,
        COALESCE(i.maximum_stock, 50) AS "maxStock",
        COALESCE(i.inventory_value, COALESCE(i.current_stock, 0) * COALESCE(p.standard_cost, 0.0)) AS inventory_value,
        i.last_receipt_date,
        i.last_issue_date,
        COALESCE(i.last_updated, p.created_date, NOW()) AS last_updated,
        COALESCE(i.last_updated, p.created_date, NOW()) AS updated_at
    FROM parts p
    LEFT JOIN inventory i ON i.part_id = p.part_id
    ORDER BY p.part_name ASC
"""

SELECT_INVENTORY_BY_PART_ID = """
    SELECT 
        COALESCE(i.inventory_id, p.part_id) AS id,
        i.inventory_id,
        p.part_id,
        p.part_number,
        p.part_number AS sku,
        p.part_name,
        p.part_name AS name,
        p.part_name AS part,
        p.category,
        p.sub_category,
        COALESCE(p.criticality, 'Essential') AS criticality,
        COALESCE(p.standard_cost, 0.0) AS standard_cost,
        COALESCE(p.standard_cost, 0.0) AS unit_cost,
        COALESCE(i.average_unit_cost, p.standard_cost, 0.0) AS average_unit_cost,
        COALESCE(i.current_stock, 0) AS current_stock,
        COALESCE(i.current_stock, 0) AS quantity,
        COALESCE(i.current_stock, 0) AS "currentStock",
        COALESCE(i.reserved_stock, 0) AS reserved_stock,
        COALESCE(i.available_stock, COALESCE(i.current_stock, 0) - COALESCE(i.reserved_stock, 0)) AS available_stock,
        COALESCE(i.stock_in_transit, 0) AS stock_in_transit,
        COALESCE(i.reorder_point, p.reorder_point, 10) AS reorder_point,
        COALESCE(i.reorder_point, p.reorder_point, 10) AS "reorderPoint",
        COALESCE(i.safety_stock, p.safety_stock, 5) AS safety_stock,
        COALESCE(i.safety_stock, p.safety_stock, 5) AS "safetyStock",
        COALESCE(i.maximum_stock, 50) AS maximum_stock,
        COALESCE(i.maximum_stock, 50) AS max_stock,
        COALESCE(i.maximum_stock, 50) AS "maxStock",
        COALESCE(i.inventory_value, COALESCE(i.current_stock, 0) * COALESCE(p.standard_cost, 0.0)) AS inventory_value,
        i.last_receipt_date,
        i.last_issue_date,
        COALESCE(i.last_updated, p.created_date, NOW()) AS last_updated,
        COALESCE(i.last_updated, p.created_date, NOW()) AS updated_at
    FROM parts p
    LEFT JOIN inventory i ON i.part_id = p.part_id
    WHERE p.part_id = %s
"""

UPSERT_INVENTORY = """
    INSERT INTO inventory 
    (part_id, current_stock, reserved_stock, available_stock, stock_in_transit, 
     reorder_point, safety_stock, maximum_stock, average_unit_cost, inventory_value, last_updated)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (part_id) DO UPDATE
    SET current_stock = EXCLUDED.current_stock,
        reserved_stock = EXCLUDED.reserved_stock,
        available_stock = EXCLUDED.available_stock,
        stock_in_transit = EXCLUDED.stock_in_transit,
        reorder_point = EXCLUDED.reorder_point,
        safety_stock = EXCLUDED.safety_stock,
        maximum_stock = EXCLUDED.maximum_stock,
        average_unit_cost = EXCLUDED.average_unit_cost,
        inventory_value = EXCLUDED.inventory_value,
        last_updated = NOW()
"""

# Demand History Queries
SELECT_DEMAND_HISTORY = """
    SELECT 
        dh.*,
        p.part_number,
        p.part_number AS sku,
        p.part_name
    FROM demand_history dh
    JOIN parts p ON p.part_id = dh.part_id
    WHERE 1=1
"""

UPSERT_DEMAND_HISTORY = """
    INSERT INTO demand_history (part_id, date, quantity_consumed, depot)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (part_id, date, depot) DO UPDATE
    SET quantity_consumed = EXCLUDED.quantity_consumed
    RETURNING *
"""

# Forecast Queries
SELECT_FORECASTS = """
    SELECT 
        f.*,
        p.part_number,
        p.part_number AS sku,
        p.part_name
    FROM forecasts f
    JOIN parts p ON p.part_id = f.part_id
    WHERE 1=1
"""

INSERT_FORECAST = """
    INSERT INTO forecasts (part_id, forecast_date, forecast_quantity, model_name, model_version)
    VALUES (%s, %s, %s, %s, %s)
"""

# PuLP Input Query
SELECT_PULP_OPTIMIZATION_INPUT = """
    SELECT 
        p.part_id,
        p.part_number,
        p.part_number AS sku,
        p.part_name,
        p.part_name AS name,
        p.category,
        COALESCE(p.criticality, 'Essential') AS criticality,
        COALESCE(i.current_stock, 0) AS current_inventory,
        COALESCE(i.reorder_point, p.reorder_point, 10) AS reorder_point,
        COALESCE(i.safety_stock, p.safety_stock, 5) AS safety_stock,
        COALESCE(i.maximum_stock, 50) AS max_stock,
        COALESCE(latest_fc.forecast_quantity, 15.0) AS forecast_demand,
        latest_po.vendor_id,
        latest_po.vendor_id AS supplier_id,
        v.vendor_name,
        v.vendor_name AS supplier_name,
        COALESCE(latest_po.unit_price, p.standard_cost, 0.0) AS supplier_unit_cost,
        COALESCE(p.lead_time_days, v.default_lead_time_days, 7) AS lead_time_days,
        COALESCE(p.minimum_order_quantity, 1) AS minimum_order_quantity
    FROM parts p
    LEFT JOIN inventory i ON i.part_id = p.part_id
    LEFT JOIN LATERAL (
        SELECT forecast_quantity 
        FROM forecasts f 
        WHERE f.part_id = p.part_id 
        ORDER BY forecast_date DESC 
        LIMIT 1
    ) latest_fc ON true
    LEFT JOIN LATERAL (
        SELECT po.vendor_id, poi.unit_price
        FROM purchase_order_items poi
        JOIN purchase_orders po ON po.po_id = poi.po_id
        WHERE poi.part_id = p.part_id
        ORDER BY po.po_date DESC NULLS LAST, po.po_id DESC
        LIMIT 1
    ) latest_po ON true
    LEFT JOIN vendors v ON v.vendor_id = latest_po.vendor_id
    ORDER BY p.part_name ASC
"""
