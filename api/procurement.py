"""
Procurement & PuLP Optimization API Router.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status

from utils.validation import verify_api_key
from services.procurement_service import ProcurementService
from schemas.procurement import (
    PuLPOptimizationInputResponse,
    ProcurementOptimizationRequest,
    ProcurementOptimizationResponse,
    ProcurementRecommendationCreate,
    ProcurementRecommendationBatchCreate,
    ProcurementRecommendationResponse,
)

router = APIRouter(tags=["Procurement Optimization"])


@router.get("/procurement/optimization-input", response_model=PuLPOptimizationInputResponse)
def get_pulp_optimization_input():
    return ProcurementService.get_pulp_optimization_input()


@router.post("/procurement/optimize")
@router.get("/procurement/optimize")
def optimize_procurement(request: Optional[ProcurementOptimizationRequest] = None):
    """
    Executes PuLP mixed-integer linear programming optimization.
    Considers current stock, safety stock, reorder point, supplier MOQ, lead times, and demand forecast.
    Returns recommended purchase order quantities.
    """
    return ProcurementService.optimize_procurement(request)


@router.get("/procurement-recommendations", response_model=List[ProcurementRecommendationResponse])
def get_procurement_recommendations(
    priority: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    return ProcurementService.get_recommendations(priority, limit)


@router.post("/procurement-recommendations", status_code=201, dependencies=[Depends(verify_api_key)])
def store_procurement_recommendations(payload: ProcurementRecommendationCreate | ProcurementRecommendationBatchCreate):
    items = [payload] if isinstance(payload, ProcurementRecommendationCreate) else payload.recommendations
    from database.connection import get_db_connection
    with get_db_connection() as conn:
        with conn.transaction():
            count = 0
            for rec in items:
                est_cost = rec.estimated_cost
                if est_cost is None:
                    est_cost = rec.recommended_quantity * rec.unit_cost

                conn.execute(
                    """INSERT INTO procurement_recommendations 
                       (part_id, recommended_quantity, unit_cost, estimated_cost, priority, reason, model_name)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (rec.part_id, rec.recommended_quantity, rec.unit_cost, est_cost, rec.priority, rec.reason, rec.model_name),
                )
                count += 1
            return {"status": "ok", "recommendations_stored": count}
