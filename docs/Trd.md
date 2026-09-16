# Technical Requirements Document (TRD)

## System Requirements

### Functional Requirements
1. **Natural Language Processing**
   - Accept free-form travel requests
   - Extract structured profile with hard/soft constraint classification
   - Handle missing field detection and clarification requests

2. **Multi-Agent Orchestration**
   - Supervisor coordinates 8+ specialized agents
   - Typed JSON/Pydantic message contracts
   - Dependency tracking and state management
   - Deterministic task decomposition

3. **Retrieval & Ranking**
   - Vector-based semantic POI matching
   - Multi-criteria scoring: relevance, quality, cost, time, distance
   - Evidence storage with source metadata and timestamps
   - Filter by category, accessibility, price range, operating hours

4. **Route Planning**
   - Mode-specific travel time and distance estimation
   - Route matrix generation
   - Visit-order optimization (TSP/Orienteering with time windows)
   - Detour and excessive-travel detection

5. **Constraint Management**
   - Budget tracking (cumulative and per-day)
   - Opening hours validation
   - Daily time-limit enforcement
   - Accessibility requirement checks
   - Hard vs. soft constraint separation

6. **Itinerary Generation**
   - Day-wise schedule with time blocks
   - Activity, meal, transfer, rest period allocation
   - Cost and travel estimates per day
   - Evidence-linked explanations

7. **Verification & Validation**
   - Independent critic agent checks
   - Hallucination detection (unsupported claims)
   - Time overlap and duplicate POI detection
   - Closed venue and missing transfer checks
   - Constraint violation reporting

8. **Replanning**
   - Targeted agent re-invocation for conflicts
   - Partial vs. full replanning logic
   - Iterative validation until hard constraints pass
   - User feedback integration

### Non-Functional Requirements
1. **Performance**
   - Agent orchestration response < 30s for simple queries
   - Concurrent agent execution where possible
   - Caching of retrieval results (15min TTL)

2. **Reliability**
   - Schema validation on all agent messages
   - Graceful handling of tool/API failures
   - No LLM-invented operational values
   - Retry logic with exponential backoff

3. **Observability**
   - Agent trace logging (tool calls, latency, sources)
   - Schema failure tracking
   - Conflict count metrics
   - Validation status per itinerary

4. **Scalability**
   - Support 7-day trip planning
   - Handle 50+ candidate POIs per day
   - Multiple concurrent user sessions

## Technical Constraints

### Technology Stack
- **Backend**: Python 3.10+, FastAPI, LangGraph
- **Frontend**: React 18+, Next.js 14+, TypeScript 5+
- **Database**: PostgreSQL 15+ with pgvector extension
- **Libraries**: 
  - Pydantic 2.x for schema validation
  - SQLAlchemy 2.x for ORM
  - NetworkX for graph operations
  - OR-Tools for optimization
  - sentence-transformers for embeddings

### External Dependencies
- **LLM API**: OpenAI/Anthropic/equivalent with structured output support
- **Maps API**: Google Maps/Mapbox/equivalent for routing
- **Optional**: Weather API, Transit API, Traffic API

### Data Requirements
- POI database with:
  - Name, coordinates, category, description
  - Opening hours, visit duration, cost range
  - Accessibility attributes, ratings
- Embedding vectors for semantic search
- User profile and trip state persistence

## API Specifications

### Agent Communication Schema
```python
class UserProfile(BaseModel):
    destination: str
    origin: Optional[str]
    date_range: tuple[date, date]
    budget: Money
    travelers: list[Traveler]
    interests: list[str]
    constraints: dict[str, Any]
    
class POICandidate(BaseModel):
    id: str
    name: str
    coordinates: tuple[float, float]
    category: str
    evidence: Evidence
    score: float
    
class RouteMatrix(BaseModel):
    distances: dict[tuple[str, str], float]
    travel_times: dict[tuple[str, str], float]
    mode: TransportMode
    
class Conflict(BaseModel):
    severity: Literal["hard", "soft"]
    type: str
    affected_item: str
    reason: str
    repair_action: str
```

### REST API Endpoints
- `POST /api/trips` - Create new trip planning job
- `GET /api/trips/{id}` - Get trip status
- `GET /api/trips/{id}/itinerary` - Get validated itinerary
- `PATCH /api/trips/{id}` - Update preferences (triggers replan)
- `POST /api/trips/{id}/feedback` - Submit user feedback

## Security & Privacy
- No storage of payment credentials
- User profile data encryption at rest
- API key management via environment variables
- Rate limiting on public endpoints

## Testing Requirements
- Unit tests for each agent (>80% coverage)
- Integration tests for orchestration flow
- End-to-end tests with representative queries
- Constraint violation detection tests
- Baseline comparison tests (single-agent, rule-based)
