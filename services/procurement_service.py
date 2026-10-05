"""
Procurement Service bridging database queries, PuLP optimization engine, and procurement recommendations.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import HTTPException

from database.connection import get_db_connection
from database.queries import SELECT_PULP_OPTIMIZATION_INPUT
from schemas.procurement import (
    PuLPOptimizationInputItem,
    PuLPOptimizationInputResponse,
    ProcurementOptimizationRequest,
    ProcurementOptimizationResponse,
    ProcurementRecommendationCreate,
    ProcurementRecommendationBatchCreate,
    ProcurementRecommendationResponse,
)
from ml.procurement.optimize import run_procurement_optimization

logger = logging.getLogger("ksrtc_backend.services.procurement")
DEPOT_NAME = "KSRTC Central Stores"


class ProcurementService:
    @staticmethod
    def get_pulp_optimization_input() -> PuLPOptimizationInputResponse:
        try:
            with get_db_connection() as conn:
                rows = conn.execute(SELECT_PULP_OPTIMIZATION_INPUT).fetchall()
                items = [PuLPOptimizationInputItem(**dict(r)) for r in rows]
                return PuLPOptimizationInputResponse(
                    depot=DEPOT_NAME,
                    generated_at=datetime.now(timezone.utc),
                    items=items,
                )
        except Exception as e:
            logger.warning(f"Could not fetch PuLP optimization input from DB ({e}); using offline baseline input.")
            items = [
                PuLPOptimizationInputItem(
                    part_id=1,
                    sku="ENG-AL-001",
                    name="Engine Oil Filter Spin-On",
                    category="Engine",
                    criticality="Critical",
                    current_inventory=5,
                    reorder_point=30,
                    safety_stock=15,
                    max_stock=80,
                    forecast_demand=25.0,
                    supplier_unit_cost=850.0,
                    lead_time_days=7,
                    minimum_order_quantity=10,
                )
            ]
            return PuLPOptimizationInputResponse(
                depot=DEPOT_NAME,
                generated_at=datetime.now(timezone.utc),
                items=items,
            )


    @staticmethod
    def optimize_procurement(request: Optional[ProcurementOptimizationRequest] = None) -> Dict[str, Any]:
        """
        Executes PuLP linear programming optimization across catalog items.
        Stores generated recommendations in DB for historical tracking.
        """
        inp = ProcurementService.get_pulp_optimization_input()
        parts_list = [item.model_dump() for item in inp.items]

        budget = request.total_budget if request else None
        if request and request.parts_filter:
            filter_set = set(request.parts_filter)
            parts_list = [p for p in parts_list if p["part_id"] in filter_set]

        opt_result = run_procurement_optimization(parts_list, total_budget=budget)

        # Automatically store recommendations in DB for persistence
        if opt_result.get("recommendations"):
            try:
                with get_db_connection() as conn:
                    with conn.transaction():
                        for rec in opt_result["recommendations"]:
                            conn.execute(
                                """INSERT INTO procurement_recommendations 
                                   (part_id, recommended_quantity, unit_cost, estimated_cost, priority, reason, model_name)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                                (
                                    rec["part_id"],
                                    rec["recommended_order_quantity"],
                                    rec["unit_cost"],
                                    rec["total_cost"],
                                    rec["priority"],
                                    rec["reason"],
                                    "PuLP-Procurement-Optimizer",
                                ),
                            )
            except Exception as e:
                logger.warning("Could not persist procurement recommendations to DB: %s", e)

        return opt_result

    @staticmethod
    def get_recommendations(priority: Optional[str] = None, limit: int = 100) -> List[dict]:
        query = """
            SELECT 
                pr.*,
                p.part_number,
                p.part_number AS sku,
                p.part_name,
                p.part_name AS part,
                p.category,
                latest_v.vendor_name AS primary_supplier
            FROM procurement_recommendations pr
            JOIN parts p ON p.part_id = pr.part_id
            LEFT JOIN LATERAL (
                SELECT v.vendor_name 
                FROM purchase_order_items poi
                JOIN purchase_orders po ON po.po_id = poi.po_id
                JOIN vendors v ON v.vendor_id = po.vendor_id
                WHERE poi.part_id = p.part_id
                ORDER BY po.po_date DESC NULLS LAST, po.po_id DESC
                LIMIT 1
            ) latest_v ON true
            WHERE 1=1
        """
        params = []
        if priority:
            query += " AND LOWER(pr.priority) = LOWER(%s)"
            params.append(priority)
        query += " ORDER BY pr.estimated_cost DESC LIMIT %s"
        params.append(limit)

        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["quantity"] = item["recommended_quantity"]
                item["unit_price"] = float(item["unit_cost"])
                item["total_cost"] = float(item["estimated_cost"])
                item["supplier"] = item.get("primary_supplier") or "Primary KSRTC Vendor"
                results.append(item)
            return results
