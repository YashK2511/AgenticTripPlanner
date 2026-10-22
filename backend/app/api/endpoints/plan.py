import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import TripStateModel, AgentTraceModel
from app.models.schemas import (
    TripPlanRequest,
    TripPlanResponse,
    UserProfile,
    POICandidate,
    RouteOptimizationResult,
    ConstraintCheck,
    ContextData,
    AgentTrace,
)
from app.orchestration.supervisor import run_trip_planner

logger = logging.getLogger("trip_planner.api.plan")

router = APIRouter()


@router.post("/start", response_model=TripPlanResponse)
def start_trip_planning(req: TripPlanRequest, db: Session = Depends(get_db)):
    """
    Initiates the end-to-end LangGraph multi-agent trip planning workflow.
    Executes profile extraction, POI retrieval, context fetch, route optimization,
    and constraint verification in a directed supervisor graph.
    """
    try:
        logger.info("Received trip plan start request")
        response = run_trip_planner(request=req, db=db)
        logger.info(
            "Trip planning workflow finished: trip_id=%s, status=%s",
            response.trip_id, response.status,
        )
        return response
    except Exception as e:
        logger.error("Trip planning workflow failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{trip_id}", response_model=TripPlanResponse)
def get_trip_plan(trip_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the persisted trip state and execution telemetry traces for a given trip ID.
    """
    trip_model = db.query(TripStateModel).filter(TripStateModel.id == trip_id).first()
    if not trip_model:
        raise HTTPException(status_code=404, detail=f"Trip plan '{trip_id}' not found")

    try:
        # Reconstruct Pydantic models from serialized JSON columns
        profile = UserProfile(**trip_model.profile_json) if trip_model.profile_json else None

        candidates = []
        if trip_model.candidates_json:
            for c_data in trip_model.candidates_json.values():
                candidates.append(POICandidate(**c_data))

        routes = RouteOptimizationResult(**trip_model.routes_json) if trip_model.routes_json else None
        constraints = ConstraintCheck(**trip_model.constraints_json) if trip_model.constraints_json else None
        context = ContextData(**trip_model.context_json) if trip_model.context_json else None

        # Fetch execution traces
        trace_models = db.query(AgentTraceModel).filter(AgentTraceModel.trip_id == trip_id).order_by(AgentTraceModel.id.asc()).all()
        traces = []
        for tm in trace_models:
            traces.append(
                AgentTrace(
                    trace_id=tm.trace_id,
                    agent_name=tm.agent_name,
                    node_name=tm.node_name,
                    status=tm.status,
                    latency_ms=tm.latency_ms,
                    input_summary=tm.input_summary_json,
                    output_summary=tm.output_summary_json,
                    error_message=tm.error_message,
                    timestamp=tm.created_at,
                )
            )

        status = "completed"
        if profile and not profile.is_complete:
            status = "incomplete_profile"

        return TripPlanResponse(
            trip_id=trip_id,
            status=status,
            profile=profile,
            clarification_questions=[],
            candidates=candidates,
            routes=routes,
            constraints=constraints,
            context=context,
            traces=traces,
        )

    except Exception as e:
        logger.error("Failed to retrieve trip plan %s: %s", trip_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
