# Design Document

## System Design Overview
The system follows a **Multi-Agent System (MAS)** architecture orchestrated by a central supervisor. Each agent is a specialized module with a clear responsibility, communicating via typed contracts (Pydantic schemas).

## Core Design Principles
1. **Separation of Concerns**: Each agent handles one responsibility (retrieval, routing, budget, synthesis, verification).
2. **Evidence-Grounded**: Every recommendation must be linked to a source (API, database, retrieval timestamp).
3. **Hard vs. Soft Constraints**: Hard constraints block publication; soft preferences are weighted and optimized.
4. **Independent Verification**: The Critic Agent validates the final itinerary independent of the synthesis process.
5. **Targeted Replanning**: Conflicts are returned to the Supervisor with the specific affected item and repair action.

## Agent Design Specifications

### 1. Supervisor/Orchestrator Agent
**Responsibility**: Central coordinator, state manager, conflict resolver.

**Inputs**:
- User request (natural language)
- Agent responses (typed JSON)
- Conflict reports from Critic

**Outputs**:
- Subtask assignments to specialized agents
- Replanning decisions
- Final validated itinerary

**Logic**:
- Parse job envelope and validate essential fields
- Create shared trip state
- Decompose request into subtasks with dependency tracking
- Route conflicts to responsible agents
- Version itinerary state for rollback

### 2. User Profile & Preference Agent
**Responsibility**: Extract structured profile from natural language.

**Inputs**: Free-form travel request text

**Outputs**: 
```python
class UserProfile(BaseModel):
    destination: str
    origin: Optional[str]
    date_range: tuple[date, date]
    budget: Money
    travelers: list[Traveler]
    interests: list[str]
    hard_constraints: dict[str, Any]
    soft_preferences: dict[str, float]  # preference: weight
    missing_fields: list[str]
```

**Logic**:
- LLM extraction with structured output schema
- Classify constraints (hard = non-negotiable, soft = weighted)
- Identify missing required fields
- Normalize dates, currency, units

### 3. Destination & POI Retrieval Agent
**Responsibility**: Fetch and filter candidate POIs, restaurants, hotels.

**Inputs**: UserProfile, destination, categories

**Outputs**:
```python
class POICandidate(BaseModel):
    id: str
    name: str
    coordinates: tuple[float, float]
    category: str
    description: str
    opening_hours: dict
    visit_duration: int  # minutes
    cost_range: tuple[float, float]
    accessibility: dict
    evidence: Evidence  # source, timestamp, API
    relevance_score: float
```

**Logic**:
- Query vector database for semantic match
- Filter by category, city, price range, accessibility
- Store retrieval timestamp and source
- Rank by multi-criteria score

### 4. Transportation & Route Planning Agent
**Responsibility**: Calculate travel times, distances, and propose efficient visit orders.

**Inputs**: List of POI coordinates, permitted transport modes

**Outputs**:
```python
class RouteMatrix(BaseModel):
    distances: dict[tuple[str, str], float]  # meters
    travel_times: dict[tuple[str, str], float]  # minutes
    mode: TransportMode
    
class VisitSequence(BaseModel):
    day: int
    ordered_pois: list[str]
    total_travel_time: float
    total_distance: float
```

**Logic**:
- Query Maps API for pairwise distances/times
- Build route matrix
- Apply visit-order heuristic (OR-Tools or 2-opt)
- Flag excessive detours (>X% extra distance)

### 5. Budget & Constraint Agent
**Responsibility**: Validate all constraints and check feasibility.

**Inputs**: POI candidates, route data, UserProfile

**Outputs**:
```python
class ConstraintCheck(BaseModel):
    passed: bool
    violations: list[Violation]
    
class Violation(BaseModel):
    type: str  # "budget", "time", "closed", "accessibility"
    severity: Literal["hard", "soft"]
    affected_item: str
    reason: str
    repair_suggestion: str
```

**Logic**:
- Aggregate costs (transport + activities + food + accommodation)
- Check opening hours vs. visit time
- Verify daily time limit (start/end times)
- Check accessibility requirements
- Validate permitted transport modes

### 6. Context Agent
**Responsibility**: Retrieve contextual data (weather, traffic, disruptions).

**Inputs**: Destination, dates

**Outputs**:
```python
class ContextData(BaseModel):
    weather: Optional[WeatherInfo]
    traffic: Optional[TrafficInfo]
    disruptions: list[Disruption]
    availability: dict[str, bool]  # what data was available
```

**Logic**:
- Query weather API if configured
- Query traffic/transit APIs if configured
- Mark fields as "unavailable" if no source configured
- Never invent values

### 7. Itinerary Synthesis Agent
**Responsibility**: Assemble validated data into a coherent day-wise schedule.

**Inputs**: Validated POIs, route sequences, constraints, context

**Outputs**:
```python
class Itinerary(BaseModel):
    days: list[DayPlan]
    total_cost: Money
    assumptions: list[str]
    warnings: list[str]
    
class DayPlan(BaseModel):
    date: date
    blocks: list[TimeBlock]
    daily_cost: Money
    daily_travel_time: float
    
class TimeBlock(BaseModel):
    type: Literal["travel", "activity", "meal", "rest", "checkin", "checkout"]
    start_time: time
    end_time: time
    poi: Optional[POICandidate]
    cost: Money
    rationale: str
```

**Logic**:
- Allocate POIs to days based on route sequences
- Insert travel blocks between activities
- Add meal blocks (lunch, dinner)
- Add rest/buffer time
- Compute arrival times considering opening hours
- Attach evidence-based rationale

### 8. Critic/Verification Agent
**Responsibility**: Independent validation before release.

**Inputs**: Complete itinerary, original UserProfile, evidence database

**Outputs**:
```python
class ValidationReport(BaseModel):
    valid: bool
    conflicts: list[Conflict]
    
class Conflict(BaseModel):
    severity: Literal["hard", "soft"]
    type: str
    affected_day: int
    affected_item: str
    reason: str
    evidence: Optional[str]
    repair_action: str
```

**Checks**:
- Unsupported claims (POI not in evidence database)
- Duplicate POIs
- Time overlaps within a day
- Closed venues (opening hours vs. visit time)
- Budget violations (recompute totals)
- Missing transfers between POIs
- Excessive daily travel time
- Accessibility requirement violations

## Data Flow Diagram
```
User Input → Supervisor
    ↓
Profile Agent → Structured Profile
    ↓
Supervisor dispatches parallel:
    ├→ Retrieval Agent → POI Candidates
    ├→ Context Agent → Weather/Traffic
    └→ (waits for above)
        ↓
    Route Agent → Route Matrix + Sequences
        ↓
    Budget Agent → Constraint Checks
        ↓
    Synthesis Agent → Draft Itinerary
        ↓
    Critic Agent → Validation Report
        ↓
    [IF violations] → Supervisor → Replanning
    [IF valid] → Output to User
```

## Shared State Schema
```python
class TripState(BaseModel):
    id: str
    profile: UserProfile
    candidates: dict[str, POICandidate]
    routes: RouteMatrix
    constraints: ConstraintCheck
    context: ContextData
    itinerary_versions: list[Itinerary]
    current_version: int
    validation_status: ValidationReport
    created_at: datetime
    updated_at: datetime
```

## Replanning Strategy
1. **Trigger**: Critic reports violations
2. **Analyze**: Supervisor identifies affected agent (retrieval, route, synthesis)
3. **Scope**: Determine if partial or full replan needed
   - Replace single POI → Retrieval + Route (partial)
   - Budget exceeded → Budget + Synthesis (partial)
   - Date change → Full replan
4. **Execute**: Re-invoke only affected agents
5. **Validate**: Send updated itinerary back to Critic
6. **Iterate**: Repeat until hard constraints pass or declare infeasible

## UI/UX Design Considerations
- **Progressive Disclosure**: Show high-level itinerary first, expand for details
- **Evidence Links**: Each recommendation links to source (reviews, photos, hours)
- **Assumption Visibility**: Clearly mark estimates vs. verified data
- **Conflict Visualization**: Highlight violations with repair suggestions
- **Inline Editing**: Allow users to swap POIs, adjust times, trigger replan
- **Cost Breakdown**: Per-day and total with category breakdown
- **Map Integration**: Visual route overlay with time/distance annotations

## Error Handling
- **Tool Failures**: Log, retry with backoff, fallback to cached/default data
- **LLM Schema Violations**: Validate with Pydantic, retry with corrected prompt
- **API Rate Limits**: Queue requests, cache results (15min TTL)
- **Infeasible Requests**: Return clear explanation of constraint conflicts
- **Missing Data**: Mark as "unavailable", never invent values

## Observability & Debugging
- **Agent Traces**: Log all agent inputs/outputs with timestamps
- **Provenance Tracking**: Every data point links to source
- **Validation Logs**: Record all constraint checks and outcomes
- **Performance Metrics**: Agent latency, API call counts, cache hit rates
