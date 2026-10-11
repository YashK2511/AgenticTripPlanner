import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ConstraintCheck,
    BudgetBreakdown,
    ConstraintCheckRequest,
)
from app.agents.constraint_agent import validate_constraints, compute_budget_breakdown

logger = logging.getLogger("trip_planner.api.constraints")

router = APIRouter()


@router.post("/validate", response_model=ConstraintCheck)
def validate_trip_constraints(req: ConstraintCheckRequest):
    """
    Deterministically validates candidate POIs against the user profile's
    budget ceiling, accessibility needs, opening hours, and daily time limits.
    """
    if not req.candidates:
        raise HTTPException(status_code=400, detail="Candidates list cannot be empty")

    try:
        check = validate_constraints(
            profile=req.profile,
            candidates=req.candidates,
            route_result=req.route_result,
        )
        return check
    except Exception as e:
        logger.error("Constraint validation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/budget", response_model=BudgetBreakdown)
def get_budget_breakdown(req: ConstraintCheckRequest):
    """
    Calculates itemized cost diagnostics (activities min/max, transit estimates)
    and verifies if the trip is within budget.
    """
    try:
        breakdown = compute_budget_breakdown(
            profile=req.profile,
            candidates=req.candidates,
        )
        return breakdown
    except Exception as e:
        logger.error("Budget breakdown calculation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
