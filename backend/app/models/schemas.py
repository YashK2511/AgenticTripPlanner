from typing import List, Optional, Literal, Dict, Any, Tuple
from pydantic import BaseModel, ConfigDict, Field
from datetime import date, time, datetime

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
    soft_preferences: Dict[str, float] = Field(default_factory=dict) # preference: weight
    missing_fields: List[str] = Field(default_factory=list)

class Evidence(BaseModel):
    source_id: str
    source_type: str # e.g., "google_places", "internal_db"
    retrieved_at: datetime
    url: Optional[str] = None

class POICandidate(BaseModel):
    id: str
    name: str
    coordinates: Tuple[float, float]
    category: str
    description: str
    opening_hours: Dict[str, Any] = Field(default_factory=dict)
    visit_duration: int # in minutes
    cost_range: Tuple[float, float]
    accessibility: Dict[str, bool] = Field(default_factory=dict)
    evidence: Evidence
    relevance_score: float

class TransportMode(BaseModel):
    mode: Literal["walking", "transit", "driving", "bicycling"]

class RouteMatrix(BaseModel):
    distances: Dict[str, float]  # stringified tuple key to float mapping (in meters)
    travel_times: Dict[str, float]  # stringified tuple key to float mapping (in minutes)
    mode: TransportMode

class Violation(BaseModel):
    type: str # "budget", "time", "closed", "accessibility"
    severity: Literal["hard", "soft"]
    affected_item: str
    reason: str
    repair_suggestion: str

class ConstraintCheck(BaseModel):
    passed: bool
    violations: List[Violation] = Field(default_factory=list)

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
