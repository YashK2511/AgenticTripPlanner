import uuid
import time
import logging
import operator
from datetime import datetime, timezone
from typing import TypedDict, Annotated, List, Optional, Dict, Any, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RunnableConfig
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.db_models import TripStateModel, AgentTraceModel
from app.models.schemas import (
    UserProfile,
    POICandidate,
    RouteOptimizationResult,
    ConstraintCheck,
    ContextData,
    AgentTrace,
    TripPlanRequest,
    TripPlanResponse,
    RouteMatrix,
    TransportMode,
)
from app.agents.profile_agent import extract_profile
from app.agents.poi_retrieval_agent import retrieve_pois
from app.agents.context_agent import fetch_context
from app.agents.route_agent import compute_route_matrix, solve_visit_sequence
from app.agents.constraint_agent import validate_constraints

logger = logging.getLogger("trip_planner.orchestration.supervisor")


# ──────────────────────── PlanState Definition ────────────────────────

class PlanState(TypedDict):
    trip_id: str
    user_request: Optional[str]
    mode: Literal["walking", "transit", "driving", "bicycling"]
    max_hours_per_day: float
    profile: Optional[UserProfile]
    is_profile_complete: bool
    clarification_questions: List[str]
    candidates: List[POICandidate]
    routes: Optional[RouteOptimizationResult]
    constraints: Optional[ConstraintCheck]
    context: Optional[ContextData]
    traces: Annotated[List[AgentTrace], operator.add]
    status: str  # "in_progress" | "incomplete_profile" | "completed" | "failed"
    error: Optional[str]


# ──────────────────────── Node Functions ───────────────────────────────

def profile_extract_node(state: PlanState) -> Dict[str, Any]:
    """
    Node 1: Extract or validate UserProfile from user request or pre-supplied profile.
    """
    start_time = time.perf_counter()
    trace_id = str(uuid.uuid4())
    agent_name = "profile_agent"
    node_name = "profile_extract"

    try:
        profile = state.get("profile")
        if profile is None and state.get("user_request"):
            result = extract_profile(state["user_request"])
            profile = result.profile

        if profile is None:
            raise ValueError("No profile or request text provided to extract_profile")

        is_complete = profile.is_complete
        clarification_questions = []
        if not is_complete:
            from app.agents.profile_agent import _generate_clarification_questions
            clarification_questions = _generate_clarification_questions(profile)

        req_len = len(state.get("user_request") or "")
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="success",
            latency_ms=round(latency_ms, 2),
            input_summary={"request_len": req_len},
            output_summary={
                "destination": profile.destination,
                "is_complete": is_complete,
                "travelers_count": len(profile.travelers),
            },
        )

        status = "in_progress" if is_complete else "incomplete_profile"
        return {
            "profile": profile,
            "is_profile_complete": is_complete,
            "clarification_questions": clarification_questions,
            "status": status,
            "traces": [trace],
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("profile_extract_node failed: %s", e, exc_info=True)
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="error",
            latency_ms=round(latency_ms, 2),
            error_message=str(e),
        )
        return {
            "status": "failed",
            "error": str(e),
            "traces": [trace],
        }


def poi_retrieval_node(state: PlanState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Node 2: Retrieve POI candidates from vector/relational database based on profile.
    """
    start_time = time.perf_counter()
    trace_id = str(uuid.uuid4())
    agent_name = "poi_retrieval_agent"
    node_name = "poi_retrieval"

    try:
        profile = state["profile"]
        db: Session = config.get("configurable", {}).get("db")
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            candidates = retrieve_pois(profile=profile, db=db, top_k=10)
        finally:
            if close_db:
                db.close()

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="success",
            latency_ms=round(latency_ms, 2),
            input_summary={"destination": profile.destination, "interests": profile.interests},
            output_summary={"candidates_count": len(candidates)},
        )

        return {
            "candidates": candidates,
            "traces": [trace],
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("poi_retrieval_node failed: %s", e, exc_info=True)
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="error",
            latency_ms=round(latency_ms, 2),
            error_message=str(e),
        )
        return {
            "status": "failed",
            "error": str(e),
            "traces": [trace],
        }


def context_fetch_node(state: PlanState) -> Dict[str, Any]:
    """
    Node 3: Fetch external environmental context (weather forecast, disruptions).
    """
    start_time = time.perf_counter()
    trace_id = str(uuid.uuid4())
    agent_name = "context_agent"
    node_name = "context_fetch"

    try:
        profile = state["profile"]
        context_data = fetch_context(
            destination=profile.destination,
            start_date=profile.start_date,
            end_date=profile.end_date,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="success",
            latency_ms=round(latency_ms, 2),
            input_summary={"destination": profile.destination},
            output_summary={
                "weather_available": context_data.availability.get("weather", False),
                "disruptions_count": len(context_data.disruptions),
            },
        )

        return {
            "context": context_data,
            "traces": [trace],
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("context_fetch_node failed: %s", e, exc_info=True)
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="error",
            latency_ms=round(latency_ms, 2),
            error_message=str(e),
        )
        return {
            "context": ContextData(availability={"weather": False, "traffic": False}),
            "traces": [trace],
        }


def route_optimize_node(state: PlanState) -> Dict[str, Any]:
    """
    Node 4: Compute distance/time matrix and optimize visit sequencing via OR-Tools.
    """
    start_time = time.perf_counter()
    trace_id = str(uuid.uuid4())
    agent_name = "route_agent"
    node_name = "route_optimize"

    try:
        candidates = state.get("candidates", [])
        profile = state["profile"]
        mode = state.get("mode", "driving")
        max_hours = state.get("max_hours_per_day", 8.0)

        if not candidates:
            matrix = RouteMatrix(distances={}, travel_times={}, mode=TransportMode(mode=mode))
            result = RouteOptimizationResult(
                matrix=matrix,
                daily_sequences=[],
                total_distance_meters=0.0,
                total_travel_time_minutes=0.0,
            )
        else:
            matrix = compute_route_matrix(pois=candidates, mode=mode)
            result = solve_visit_sequence(
                pois=candidates,
                matrix=matrix,
                num_days=profile.trip_duration_days,
                max_hours_per_day=max_hours,
            )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="success",
            latency_ms=round(latency_ms, 2),
            input_summary={"candidates_count": len(candidates), "num_days": profile.trip_duration_days},
            output_summary={
                "total_distance_meters": result.total_distance_meters,
                "daily_sequences_count": len(result.daily_sequences),
            },
        )

        return {
            "routes": result,
            "traces": [trace],
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("route_optimize_node failed: %s", e, exc_info=True)
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="error",
            latency_ms=round(latency_ms, 2),
            error_message=str(e),
        )
        return {
            "status": "failed",
            "error": str(e),
            "traces": [trace],
        }


def constraint_check_node(state: PlanState) -> Dict[str, Any]:
    """
    Node 5: Deterministically validate budget, accessibility, opening hours, and time limits.
    """
    start_time = time.perf_counter()
    trace_id = str(uuid.uuid4())
    agent_name = "constraint_agent"
    node_name = "constraint_check"

    try:
        profile = state["profile"]
        candidates = state.get("candidates", [])
        routes = state.get("routes")
        max_hours = state.get("max_hours_per_day", 8.0)

        check = validate_constraints(
            profile=profile,
            candidates=candidates,
            route_result=routes,
            max_daily_hours=max_hours,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="success",
            latency_ms=round(latency_ms, 2),
            input_summary={"candidates_count": len(candidates), "budget": profile.budget.amount},
            output_summary={"passed": check.passed, "violations_count": len(check.violations)},
        )

        return {
            "constraints": check,
            "traces": [trace],
        }

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("constraint_check_node failed: %s", e, exc_info=True)
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            node_name=node_name,
            status="error",
            latency_ms=round(latency_ms, 2),
            error_message=str(e),
        )
        return {
            "status": "failed",
            "error": str(e),
            "traces": [trace],
        }


def persist_state_node(state: PlanState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Node 6: Persist final trip state and execution telemetry traces into database.
    """
    start_time = time.perf_counter()
    trace_id = str(uuid.uuid4())
    agent_name = "supervisor"
    node_name = "persist_state"

    trip_id = state["trip_id"]
    status = state.get("status", "completed")
    if status == "in_progress":
        status = "completed"

    db: Session = config.get("configurable", {}).get("db")
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Upsert TripStateModel
        trip_model = db.query(TripStateModel).filter(TripStateModel.id == trip_id).first()
        profile_dict = state["profile"].model_dump(mode="json") if state.get("profile") else None
        candidates_dict = {c.id: c.model_dump(mode="json") for c in state.get("candidates", [])}
        routes_dict = state["routes"].model_dump(mode="json") if state.get("routes") else None
        constraints_dict = state["constraints"].model_dump(mode="json") if state.get("constraints") else None
        context_dict = state["context"].model_dump(mode="json") if state.get("context") else None

        if trip_model is None:
            trip_model = TripStateModel(
                id=trip_id,
                profile_json=profile_dict,
                candidates_json=candidates_dict,
                routes_json=routes_dict,
                constraints_json=constraints_dict,
                context_json=context_dict,
                current_version=1,
            )
            db.add(trip_model)
        else:
            trip_model.profile_json = profile_dict
            trip_model.candidates_json = candidates_dict
            trip_model.routes_json = routes_dict
            trip_model.constraints_json = constraints_dict
            trip_model.context_json = context_dict
            trip_model.current_version = (trip_model.current_version or 0) + 1

        # Persist new traces
        for t in state.get("traces", []):
            existing_trace = db.query(AgentTraceModel).filter(
                AgentTraceModel.trip_id == trip_id,
                AgentTraceModel.trace_id == t.trace_id,
            ).first()
            if not existing_trace:
                trace_rec = AgentTraceModel(
                    trip_id=trip_id,
                    trace_id=t.trace_id,
                    agent_name=t.agent_name,
                    node_name=t.node_name,
                    status=t.status,
                    latency_ms=t.latency_ms,
                    input_summary_json=t.input_summary,
                    output_summary_json=t.output_summary,
                    error_message=t.error_message,
                )
                db.add(trace_rec)

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error("persist_state_node failed to write to DB: %s", e, exc_info=True)
    finally:
        if close_db:
            db.close()

    latency_ms = (time.perf_counter() - start_time) * 1000.0
    trace = AgentTrace(
        trace_id=trace_id,
        agent_name=agent_name,
        node_name=node_name,
        status="success",
        latency_ms=round(latency_ms, 2),
        output_summary={"trip_id": trip_id, "final_status": status},
    )

    return {
        "status": status,
        "traces": [trace],
    }


# ──────────────────────── Conditional Routing ─────────────────────────

def should_continue_workflow(state: PlanState) -> Literal["poi_retrieval", "persist_state"]:
    """
    Decides whether to proceed with retrieval & optimization or exit early
    if the profile is incomplete or an error occurred.
    """
    if not state.get("is_profile_complete", False) or state.get("status") in ("incomplete_profile", "failed"):
        return "persist_state"
    return "poi_retrieval"


# ──────────────────────── Graph Assembly ──────────────────────────────

def build_supervisor_graph(checkpointer: Optional[Any] = None):
    workflow = StateGraph(PlanState)

    workflow.add_node("profile_extract", profile_extract_node)
    workflow.add_node("poi_retrieval", poi_retrieval_node)
    workflow.add_node("context_fetch", context_fetch_node)
    workflow.add_node("route_optimize", route_optimize_node)
    workflow.add_node("constraint_check", constraint_check_node)
    workflow.add_node("persist_state", persist_state_node)

    workflow.add_edge(START, "profile_extract")
    workflow.add_conditional_edges(
        "profile_extract",
        should_continue_workflow,
        {
            "poi_retrieval": "poi_retrieval",
            "persist_state": "persist_state",
        },
    )
    workflow.add_edge("poi_retrieval", "context_fetch")
    workflow.add_edge("context_fetch", "route_optimize")
    workflow.add_edge("route_optimize", "constraint_check")
    workflow.add_edge("constraint_check", "persist_state")
    workflow.add_edge("persist_state", END)

    if checkpointer is None:
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)


# Compiled singleton supervisor graph
_SUPERVISOR_GRAPH = build_supervisor_graph()


def run_trip_planner(
    request: TripPlanRequest,
    trip_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> TripPlanResponse:
    """
    Public entrypoint to execute the LangGraph trip planning workflow.
    """
    t_id = trip_id or f"trip_{uuid.uuid4().hex[:12]}"
    logger.info("Starting trip planning workflow trip_id=%s", t_id)

    initial_state: PlanState = {
        "trip_id": t_id,
        "user_request": request.request_text,
        "mode": request.mode,
        "max_hours_per_day": request.max_hours_per_day,
        "profile": request.user_profile,
        "is_profile_complete": False,
        "clarification_questions": [],
        "candidates": [],
        "routes": None,
        "constraints": None,
        "context": None,
        "traces": [],
        "status": "in_progress",
        "error": None,
    }

    config = {
        "configurable": {
            "thread_id": t_id,
            "db": db,
        }
    }

    final_state = _SUPERVISOR_GRAPH.invoke(initial_state, config=config)

    return TripPlanResponse(
        trip_id=t_id,
        status=final_state.get("status", "completed"),
        profile=final_state.get("profile"),
        clarification_questions=final_state.get("clarification_questions", []),
        candidates=final_state.get("candidates", []),
        routes=final_state.get("routes"),
        constraints=final_state.get("constraints"),
        context=final_state.get("context"),
        traces=final_state.get("traces", []),
        message=final_state.get("error"),
    )
