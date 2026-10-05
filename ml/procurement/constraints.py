"""
PuLP Constraints definition module for Procurement Optimization.
Enforces MOQ, Max Stock Caps, Inventory Balance & Safety Stock, and Budget Constraints.
"""

import pulp
from typing import Dict, List, Any, Optional


def add_procurement_constraints(
    problem: pulp.LpProblem,
    parts_data: List[Dict[str, Any]],
    order_vars: Dict[int, pulp.LpVariable],
    order_flags: Dict[int, pulp.LpVariable],
    total_budget: Optional[float] = None,
):
    """
    Enforces operational constraints:
    1. Minimum Order Quantity (MOQ): order_vars[i] >= moq * order_flags[i]
    2. Upper Bound: order_vars[i] <= max_order_limit * order_flags[i]
    3. Target Safety Stock & Reorder Point Coverage
    4. Optional Budget Constraint
    """
    budget_expr = []

    for item in parts_data:
        part_id = item["part_id"]
        curr_inv = int(item.get("current_inventory", 0))
        reorder = int(item.get("reorder_point", 10))
        safety = int(item.get("safety_stock", 5))
        max_stock = int(item.get("max_stock") or item.get("maximum_stock") or 100)
        moq = int(item.get("minimum_order_quantity", 1))
        forecast = float(item.get("forecast_demand", 0.0))
        unit_cost = float(item.get("supplier_unit_cost") or item.get("standard_cost") or 0.0)

        # Upper bound limit per part order
        max_allowed_order = max(moq, max_stock - curr_inv, 200)

        # Constraint 1: Linking continuous/integer order quantity to binary order indicator flag (Big-M formulation)
        problem += (
            order_vars[part_id] >= moq * order_flags[part_id],
            f"MOQ_Constraint_Part_{part_id}",
        )
        problem += (
            order_vars[part_id] <= max_allowed_order * order_flags[part_id],
            f"MaxOrder_Constraint_Part_{part_id}",
        )

        # Constraint 2: Maximum stock limit constraint (prevent overstocking)
        problem += (
            curr_inv + order_vars[part_id] <= max_stock + moq,
            f"MaxStock_Constraint_Part_{part_id}",
        )

        # Constraint 3: Reorder & Safety stock coverage requirement
        # If current stock is below or equal to reorder point, require order to cover forecast + safety stock
        if curr_inv <= reorder:
            required_qty = max(moq, int(np_ceil(forecast + safety - curr_inv)))
            problem += (
                order_vars[part_id] >= required_qty * order_flags[part_id],
                f"SafetyStock_Coverage_Part_{part_id}",
            )
            # Force order_flag = 1 if inventory is below safety stock
            if curr_inv <= safety:
                problem += (
                    order_flags[part_id] == 1,
                    f"Mandatory_Order_Part_{part_id}",
                )

        budget_expr.append(unit_cost * order_vars[part_id])

    # Constraint 4: Optional total budget constraint
    if total_budget is not None and total_budget > 0:
        problem += (
            pulp.lpSum(budget_expr) <= total_budget,
            "Total_Budget_Cap_Constraint",
        )


def np_ceil(val: float) -> int:
    import math
    return math.ceil(max(0, val))
