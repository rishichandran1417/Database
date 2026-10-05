"""
PuLP Objective Function definition for Procurement Optimization.
Defines cost minimization objective:
Total Cost = Purchase Cost + Holding Cost + Stockout Risk Penalty
"""

import pulp
from typing import Dict, List, Any


def add_procurement_objective(
    problem: pulp.LpProblem,
    parts_data: List[Dict[str, Any]],
    order_vars: Dict[int, pulp.LpVariable],
    order_flags: Dict[int, pulp.LpVariable],
    holding_cost_rate: float = 0.10,
    stockout_penalty_multiplier: float = 2.5,
):
    """
    Formulates and attaches the PuLP objective function to minimize overall cost.

    Costs minimized:
    1. Purchase Cost: unit_cost * order_quantity
    2. Holding Cost: holding_cost_rate * unit_cost * (current_inventory + order_quantity - forecast_demand)
    3. Stockout Risk Penalty: penalize parts where (inventory + order) < forecast_demand + safety_stock
    """
    total_cost_expr = []

    for item in parts_data:
        part_id = item["part_id"]
        unit_cost = float(item.get("supplier_unit_cost") or item.get("standard_cost") or 0.0)
        criticality = item.get("criticality", "Essential")

        # Criticality weight multiplier for stockout penalty
        crit_weight = 3.0 if criticality == "Critical" else (1.5 if criticality == "High" else 1.0)

        # 1. Direct Purchase Cost
        total_cost_expr.append(unit_cost * order_vars[part_id])

        # 2. Estimated Holding Cost per ordered unit
        holding_unit_cost = holding_cost_rate * unit_cost
        total_cost_expr.append(holding_unit_cost * order_vars[part_id])

    problem += pulp.lpSum(total_cost_expr), "Total_Procurement_Cost_Minimization"
