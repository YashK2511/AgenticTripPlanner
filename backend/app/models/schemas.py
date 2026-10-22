from typing import Annotated, List, Optional, Literal, Dict, Any, Tuple
import operator
from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import date, time, datetime, timezone


# ──────────────────────── Profile & Traveler ────────────────────────

class Traveler(BaseModel):
    id: str
    age_group: Literal["adult", "child", "senior"]
    gender: Literal["male", "female", "other"]
    accessibility_needs: List[str] = Field(default_factory=list)


class Money(BaseModel):
    amount: float
    currency: str = "INR"


class UserProfile(BaseModel):
    destination: str
    origin: Optional[str] = None
    start_date: date
    end_date: date
    budget: Money
    travelers: List[Traveler]
    interests: List[str] = Field(default_factory=list)
    hard_constraints: Dict[str, Any] = Field(default_factory=dict)
    soft_preferences: Dict[str, float] = Field(default_factory=dict)  # preference: weight
    missing_fields: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @property
    def trip_duration_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def is_complete(self) -> bool:
        """True when no crucial fields are missing."""
        return len(self.missing_fields) == 0


class ProfileExtractionResult(BaseModel):
    """Wrapper around UserProfile with metadata for the API response."""
    profile: UserProfile
    is_complete: bool = Field(
        description="Whether the profile has all required fields"
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="Follow-up questions to ask the user for missing info",
    )
    request_id: str = Field(
        description="Unique identifier for tracing this extraction"
    )


class ClarificationRequest(BaseModel):
    """Request body for the /clarify endpoint."""
    request_id: str = Field(
        description="The request_id returned by the initial extraction"
    )
    original_request: str = Field(
        description="The user's original travel request text"
    )
    follow_up: str = Field(
        description="The user's follow-up answer to clarification questions"
    )
    partial_profile: Optional[UserProfile] = Field(
        default=None,
        description="The previously extracted partial profile, if available",
    )


# ──────────────────────── Evidence & POI ────────────────────────

class Evidence(BaseModel):
    source_id: str
    source_type: str  # e.g., "google_places", "internal_db"
    retrieved_at: datetime
    url: Optional[str] = None


class POICandidate(BaseModel):
    id: str
    name: str
    coordinates: Tuple[float, float]
    category: str
    description: str
    opening_hours: Dict[str, Any] = Field(default_factory=dict)
    visit_duration: int  # in minutes
    cost_range: Tuple[float, float]
    accessibility: Dict[str, bool] = Field(default_factory=dict)
    evidence: Evidence
    relevance_score: float


# ──────────────────────── Routes ────────────────────────

class TransportMode(BaseModel):
    mode: Literal["walking", "transit", "driving", "bicycling"]


class RouteMatrix(BaseModel):
    distances: Dict[str, float]  # stringified key "poi1:poi2" → meters
    travel_times: Dict[str, float]  # stringified key "poi1:poi2" → minutes
    mode: TransportMode

    def get_distance(self, from_id: str, to_id: str) -> float:
        return self.distances.get(f"{from_id}:{to_id}", 0.0)

    def get_travel_time(self, from_id: str, to_id: str) -> float:
        return self.travel_times.get(f"{from_id}:{to_id}", 0.0)


class VisitSequence(BaseModel):
    day: int
    ordered_poi_ids: List[str]
    total_distance_meters: float
    total_travel_time_minutes: float


class RouteOptimizationResult(BaseModel):
    matrix: RouteMatrix
    daily_sequences: List[VisitSequence]
    total_distance_meters: float
    total_travel_time_minutes: float


class RouteMatrixRequest(BaseModel):
    pois: List[POICandidate]
    mode: Literal["walking", "transit", "driving", "bicycling"] = "driving"


class RouteOptimizationRequest(BaseModel):
    candidates: List[POICandidate]
    num_days: int = 1
    mode: Literal["walking", "transit", "driving", "bicycling"] = "driving"
    max_hours_per_day: float = 8.0


# ──────────────────────── Constraints ────────────────────────

class Violation(BaseModel):
    type: str  # "budget", "time", "closed", "accessibility"
    severity: Literal["hard", "soft"]
    affected_item: str
    reason: str
    repair_suggestion: str


class ConstraintCheck(BaseModel):
    passed: bool
    violations: List[Violation] = Field(default_factory=list)


class BudgetBreakdown(BaseModel):
    total_budget: float
    currency: str = "INR"
    activities_min: float
    activities_max: float
    estimated_transit: float = 0.0
    estimated_total_min: float
    estimated_total_max: float
    within_budget: bool
    budget_margin_min: float


class ConstraintCheckRequest(BaseModel):
    profile: UserProfile
    candidates: List[POICandidate]
    route_result: Optional[RouteOptimizationResult] = None


# ──────────────────────── Itinerary ────────────────────────

class TimeBlock(BaseModel):
    type: Literal["travel", "activity", "meal", "rest", "checkin", "checkout"]
    start_time: time
    end_time: time
    poi: Optional[POICandidate] = None
    cost: Money
    rationale: str


class DayPlan(BaseModel):
    date: date
    blocks: List[TimeBlock] = Field(default_factory=list)
    daily_cost: Money
    daily_travel_time: float


class Itinerary(BaseModel):
    days: List[DayPlan] = Field(default_factory=list)
    total_cost: Money
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ──────────────────────── Validation ────────────────────────

class Conflict(BaseModel):
    severity: Literal["hard", "soft"]
    type: str
    affected_day: int
    affected_item: str
    reason: str
    evidence: Optional[str] = None
    repair_action: str


class ValidationReport(BaseModel):
    valid: bool
    conflicts: List[Conflict] = Field(default_factory=list)


# ──────────────────────── Trip State ────────────────────────

class TripState(BaseModel):
    id: str
    profile: Optional[UserProfile] = None
    candidates: Dict[str, POICandidate] = Field(default_factory=dict)
    routes: Optional[RouteMatrix] = None
    constraints: Optional[ConstraintCheck] = None
    itinerary_versions: List[Itinerary] = Field(default_factory=list)
    current_version: int = 0
    validation_status: Optional[ValidationReport] = None
    created_at: datetime
    updated_at: datetime


# ──────────────────────── Context & Disruptions ──────────────────────

class WeatherInfo(BaseModel):
    destination: str
    condition: str
    temperature_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    precipitation_chance: Optional[float] = 0.0
    humidity: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    forecast_days: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class Disruption(BaseModel):
    id: str
    category: str  # "weather", "traffic", "transit", "closure"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    description: str
    affected_area: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class ContextData(BaseModel):
    weather: Optional[WeatherInfo] = None
    traffic: Optional[Dict[str, Any]] = None
    disruptions: List[Disruption] = Field(default_factory=list)
    availability: Dict[str, bool] = Field(
        default_factory=lambda: {"weather": False, "traffic": False}
    )
    retrieved_at: Optional[datetime] = None


# ──────────────────────── Telemetry ──────────────────────────────────

class AgentTrace(BaseModel):
    trace_id: str
    agent_name: str
    node_name: str
    status: Literal["success", "failure", "skipped", "error"]
    latency_ms: float
    input_summary: Optional[Dict[str, Any]] = None
    output_summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ──────────────────────── Orchestrator Request / Response ─────────────

class TripPlanRequest(BaseModel):
    request_text: Optional[str] = None
    user_profile: Optional[UserProfile] = None
    mode: Literal["walking", "transit", "driving", "bicycling"] = "driving"
    max_hours_per_day: float = 8.0

    @model_validator(mode="after")
    def validate_inputs(self):
        if not self.request_text and not self.user_profile:
            raise ValueError(
                "Either request_text or user_profile must be provided"
            )
        return self


class TripPlanResponse(BaseModel):
    trip_id: str
    status: Literal["completed", "incomplete_profile", "failed", "in_progress"]
    profile: Optional[UserProfile] = None
    clarification_questions: List[str] = Field(default_factory=list)
    candidates: List[POICandidate] = Field(default_factory=list)
    routes: Optional[RouteOptimizationResult] = None
    constraints: Optional[ConstraintCheck] = None
    context: Optional[ContextData] = None
    traces: List[AgentTrace] = Field(default_factory=list)
    message: Optional[str] = None
