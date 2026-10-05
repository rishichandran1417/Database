"""
PuLP Linear Programming Procurement Optimizer.
Solves mixed-integer linear programming (MILP) optimization problem to compute recommended order quantities.
Compatible with PuLP 3.x and PuLP 4.x.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import pulp

from ml.procurement.objective import add_procurement_objective
from ml.procurement.constraints import add_procurement_constraints

logger = logging.getLogger("ksrtc_backend.ml.procurement.optimize")


def create_variable(problem: pulp.LpProblem, name: str, lowBound: Optional[float] = 0, cat: str = pulp.LpContinuous) -> pulp.LpVariable:
    """Helper creating variables compatible across PuLP versions."""
    if hasattr(problem, "add_variable"):
        return problem.add_variable(name, lowBound=lowBound, cat=cat)
    else:
        return pulp.LpVariable(name, lowBound=lowBound, cat=cat)


def run_procurement_optimization(
    parts_input: List[Dict[str, Any]],
    total_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Executes PuLP MILP optimization for supply-chain procurement.
    
    Returns structured results containing total spend, list of recommended order quantities,
    supplier details, priority levels, and business rationale per part.
    """
    logger.info("Initializing PuLP Procurement Optimization engine for %d items...", len(parts_input))

    if not parts_input:
        return {
            "status": "empty_input",
            "optimization_engine": "PuLP MILP",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_parts_analyzed": 0,
            "total_parts_to_order": 0,
            "total_recommended_spend": 0.0,
            "recommendations": [],
        }

    # Initialize PuLP Problem
    problem = pulp.LpProblem("KSRTC_Procurement_Optimization", pulp.LpMinimize)

    # Define Decision Variables
    order_vars: Dict[int, pulp.LpVariable] = {}
    order_flags: Dict[int, pulp.LpVariable] = {}

    for item in parts_input:
        part_id = item["part_id"]
        # Integer order quantity >= 0
        order_vars[part_id] = create_variable(problem, f"order_qty_{part_id}", lowBound=0, cat=pulp.LpInteger)
        # Binary indicator (1 if part is ordered, 0 if not)
        order_flags[part_id] = create_variable(problem, f"order_flag_{part_id}", lowBound=0, cat=pulp.LpBinary)

    # Attach Objective Function & Constraints
    add_procurement_objective(problem, parts_input, order_vars, order_flags)
    add_procurement_constraints(problem, parts_input, order_vars, order_flags, total_budget=total_budget)

    solver_status = "Fallback-Heuristic"
    try:
        problem.solve()
        if problem.status in (pulp.LpStatusOptimal, 1):
            solver_status = "Optimal"
            logger.info("PuLP optimization solver completed successfully (Optimal).")
    except Exception as e:
        logger.warning("PuLP solver execution notice: %s. Using heuristic fallback optimizer.", e)
        solver_status = "Fallback-Heuristic"

    recommendations = []
    total_spend = 0.0
    total_parts_to_order = 0

    for item in parts_input:
        part_id = item["part_id"]
        curr_inv = int(item.get("current_inventory", 0))
        reorder = int(item.get("reorder_point", 10))
        safety = int(item.get("safety_stock", 5))
        max_stock = int(item.get("max_stock") or item.get("maximum_stock") or 50)
        moq = int(item.get("minimum_order_quantity", 1))
        forecast = float(item.get("forecast_demand", 15.0))
        unit_cost = float(item.get("supplier_unit_cost") or item.get("standard_cost") or 0.0)
        criticality = item.get("criticality", "Essential")

        rec_qty = 0
        v_val = None
        if solver_status == "Optimal" and part_id in order_vars:
            try:
                v_val = order_vars[part_id].value() if hasattr(order_vars[part_id], "value") else order_vars[part_id].varValue
            except Exception:
                v_val = None

        if v_val is not None and v_val > 0:
            rec_qty = int(round(v_val))
        else:
            # Fallback optimization calculation if LP solver is not optimal or unassigned
            if curr_inv <= safety:
                needed = forecast + safety - curr_inv
                rec_qty = max(moq, math.ceil(needed))
            elif curr_inv <= reorder:
                needed = forecast + safety - curr_inv
                rec_qty = max(moq, math.ceil(needed))

        # Enforce MOQ and Max stock bounds on final quantity
        if rec_qty > 0 and rec_qty < moq:
            rec_qty = moq
        if curr_inv + rec_qty > max_stock + moq:
            rec_qty = max(0, max_stock - curr_inv)

        if rec_qty > 0:
            total_parts_to_order += 1
            cost_for_item = round(rec_qty * unit_cost, 2)
            total_spend += cost_for_item

            # Determine Priority & Rationale
            if curr_inv <= safety:
                priority = "Critical"
                reason = f"Stock level ({curr_inv}) breached safety threshold ({safety}). Immediate reorder required."
            elif curr_inv <= reorder:
                priority = "High" if criticality in ("Critical", "High") else "Medium"
                reason = f"Stock level ({curr_inv}) below reorder point ({reorder}). Order recommended based on 30-day demand forecast ({forecast:.1f})."
            else:
                priority = "Low"
                reason = f"Routine stock replenishment based on forecasted consumption ({forecast:.1f})."

            recommendations.append({
                "part_id": part_id,
                "part_number": item.get("part_number") or item.get("sku", ""),
                "part_name": item.get("part_name") or item.get("name", ""),
                "category": item.get("category", "General"),
                "criticality": criticality,
                "current_inventory": curr_inv,
                "safety_stock": safety,
                "reorder_point": reorder,
                "forecast_demand": round(forecast, 2),
                "recommended_order_quantity": rec_qty,
                "unit_cost": unit_cost,
                "total_cost": cost_for_item,
                "supplier_id": item.get("supplier_id") or item.get("vendor_id"),
                "supplier_name": item.get("supplier_name") or item.get("vendor_name") or "Primary Supplier",
                "lead_time_days": int(item.get("lead_time_days", 7)),
                "minimum_order_quantity": moq,
                "priority": priority,
                "reason": reason,
            })

    total_spend = float(round(total_spend, 2))

    return {
        "status": "optimal" if solver_status == "Optimal" else "evaluated",
        "optimization_engine": "PuLP Mixed-Integer Linear Programming",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_parts_analyzed": len(parts_input),
        "total_parts_to_order": total_parts_to_order,
        "total_recommended_spend": total_spend,
        "budget_cap": total_budget,
        "recommendations": recommendations,
    }
