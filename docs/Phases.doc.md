# Development Phases

## Phase 1: Foundation & Setup (Week 1-2)
### Tasks:
- [x] Environment setup (Python 3.x, FastAPI, PostgreSQL, pgvector)
- [x] Initialize project structure (backend, frontend, shared models)
- [x] Configure LLM API access and test connectivity
- [x] Set up version control and project documentation
- [x] Create database schema for trip state, profiles, and evidence
- [x] Implement basic FastAPI endpoints skeleton

## Phase 2: Profile & User Input Processing (Week 3-4)
### Tasks:
- [x] Design Pydantic schemas for user profile, constraints, and preferences
- [x] Implement User Profile & Preference Agent
- [x] Build natural-language-to-structured-profile extraction with LLM
- [x] Add validation logic for missing fields and constraint classification
- [x] Create basic web UI for trip input (React/Next.js)
- [x] Test profile extraction with representative queries

## Phase 3: Retrieval & Data Integration (Week 5-6)
### Tasks:
- [x] Set up vector database (pgvector) [via SQLite numpy fallback] for POI embeddings
- [x] Implement POI, restaurant, and accommodation retrieval agent
- [x] Integrate Maps/Places API (or fallback data sources) [seeded JSON]
- [x] Build semantic matching with sentence-transformers
- [x] Implement candidate filtering and normalization
- [x] Store evidence metadata (source, timestamp, coordinates)

## Phase 4: Route & Budget Agents (Week 7-8)
### Tasks:
- [x] Implement Transportation & Route Planning Agent
- [x] Integrate distance/travel-time estimation (Maps API or NetworkX fallback)
- [x] Build route matrix and visit-order heuristic (OR-Tools)
- [x] Implement Budget & Constraint Agent
- [x] Add checks for cost, opening hours, accessibility, daily time limits
- [x] Create machine-readable pass/fail results with explanations

## Phase 5: Orchestration & State Management (Week 9-10)
### Tasks:
- [x] Implement Supervisor/Orchestrator Agent using LangGraph
- [x] Design shared trip state schema and storage
- [x] Build task decomposition and dependency tracking
- [x] Implement agent communication via typed JSON contracts
- [x] Add Context Agent for weather/traffic (when APIs available)
- [x] Test concurrent agent execution and state updates

## Phase 6: Synthesis & Verification (Week 11-12)
### Tasks:
- [ ] Implement Itinerary Synthesis Agent
- [ ] Build day-wise schedule assembly with time blocks
- [ ] Add cost and travel estimates per day
- [ ] Implement Critic/Verification Agent
- [ ] Build independent validation checks (duplicates, overlaps, closed venues)
- [ ] Create conflict detection and structured repair requests

## Phase 7: Replanning & Feedback Loop (Week 13-14)
### Tasks:
- [ ] Implement replanning workflow in Supervisor
- [ ] Build targeted agent re-invocation for conflicts
- [ ] Add iterative validation until hard constraints pass
- [ ] Implement user feedback handling
- [ ] Add partial vs. full replanning logic
- [ ] Test end-to-end conflict resolution

## Phase 8: Testing & Evaluation (Week 15-16)
### Tasks:
- [ ] Create representative test queries (budget, duration, group variations)
- [ ] Implement baseline comparison (single-agent, rule-based)
- [ ] Measure constraint-violation counts and feasibility
- [ ] Test evidence coverage and route efficiency
- [ ] Document agent traces and observability
- [ ] Fix identified bugs and edge cases

## Phase 9: Documentation & Presentation (Week 17-18)
### Tasks:
- [ ] Complete technical documentation
- [ ] Prepare demo scenarios and screenshots
- [ ] Document known limitations and future work
- [ ] Create presentation materials
- [ ] Finalize project report
- [ ] Code cleanup and commenting
