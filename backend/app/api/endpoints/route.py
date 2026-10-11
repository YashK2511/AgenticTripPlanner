import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    RouteMatrix,
    RouteOptimizationResult,
    RouteMatrixRequest,
    RouteOptimizationRequest,
)
from app.agents.route_agent import compute_route_matrix, solve_visit_sequence

logger = logging.getLogger("trip_planner.api.route")

router = APIRouter()


@router.post("/matrix", response_model=RouteMatrix)
def get_route_matrix(req: RouteMatrixRequest):
    """
    Computes pairwise distance (meters) and travel-time (minutes) matrix
    between all candidate POIs for the requested transport mode.
    """
    if not req.pois:
        raise HTTPException(status_code=400, detail="POI list cannot be empty")

    try:
        matrix = compute_route_matrix(pois=req.pois, mode=req.mode)
        return matrix
    except Exception as e:
        logger.error("Route matrix computation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize", response_model=RouteOptimizationResult)
def optimize_route(req: RouteOptimizationRequest):
    """
    Optimizes multi-day POI visit sequencing using Google OR-Tools TSP heuristic
    and geographic clustering.
    """
    if not req.candidates:
        raise HTTPException(status_code=400, detail="Candidates list cannot be empty")

    if req.num_days < 1:
        raise HTTPException(status_code=400, detail="num_days must be at least 1")

    try:
        matrix = compute_route_matrix(pois=req.candidates, mode=req.mode)
        result = solve_visit_sequence(
            pois=req.candidates,
            matrix=matrix,
            num_days=req.num_days,
            max_hours_per_day=req.max_hours_per_day,
        )
        return result
    except Exception as e:
        logger.error("Route optimization failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
