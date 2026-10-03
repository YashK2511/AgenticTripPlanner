# Project Tracker & Todo List

## Project Milestones

- [x] **Milestone 1: Project Setup & Baseline Schemas** (Target: Phase 1)
- [x] **Milestone 2: Profile Extraction & Natural Language Parser** (Target: Phase 2)
- [x] **Milestone 3: Data Ingestion & Vector Retrieval Pipeline** (Target: Phase 3)
- [ ] **Milestone 4: Route Matrix & Budget Deterministic Solvers** (Target: Phase 4)
- [ ] **Milestone 5: LangGraph Multi-Agent Orchestrator** (Target: Phase 5)
- [ ] **Milestone 6: Itinerary Synthesis & Critic Verifier** (Target: Phase 6)
- [ ] **Milestone 7: Replanning Feedback Loop & Frontend UI** (Target: Phase 7)
- [ ] **Milestone 8: Benchmarking, Testing & Evaluation** (Target: Phase 8)

---

## Detailed Task Tracker

### Phase 1: Environment & Setup
- [x] Initialize Python environment and install dependencies (`FastAPI`, `LangGraph`, `pgvector`, `Pydantic v2`, `SQLAlchemy`)
- [x] Set up PostgreSQL database with `pgvector` extension
- [x] Establish directory structure (`backend/`, `frontend/`, `docs/`, `tests/`)
- [x] Configure environment variables (`.env.example`) and logging harness

### Phase 2: User Profile & Constraint Extraction
- [x] Implement `UserProfile` Pydantic models (hard vs soft constraints)
- [x] Build Profile Agent prompt template and LLM schema validation
- [x] Add missing field detection and clarification prompts
- [x] Write unit tests for profile extraction

### Phase 3: Retrieval & Grounding (RAG)
- [x] Seed POI, restaurant, and hotel sample data into PostgreSQL
- [x] Generate vector embeddings using `sentence-transformers`
- [x] Implement POI Retrieval Agent with metadata filtering (hours, budget, accessibility)
- [x] Ensure source evidence metadata is attached to all returned candidates

### Phase 4: Route & Budget Engines
- [ ] Build Route Agent for distance matrix computation (OSRM / Maps API)
- [ ] Implement visit-order sequencing heuristic using OR-Tools (TSP with time windows)
- [ ] Implement Budget & Constraint Agent for cost and schedule feasibility validation
- [ ] Add pass/fail violation object generators

### Phase 5: Multi-Agent Orchestration
- [ ] Construct LangGraph state graph for supervisor-coordinated agent flow
- [ ] Implement shared trip state schema and history tracking
- [ ] Add Context Agent for weather and disruption data
- [ ] Set up trace logging for agent provenance and telemetry

### Phase 6: Synthesis & Critic Verification
- [ ] Implement Itinerary Synthesis Agent to generate daily time blocks (activity, travel, meals, rest)
- [ ] Build Critic / Verification Agent for independent constraint checking
- [ ] Implement detection for hallucinated POIs, closed venues, and overlapping schedules
- [ ] Build conflict reporting schema

### Phase 7: Replanning & Frontend Interface
- [ ] Build automated targeted replanning loop in Supervisor
- [ ] Initialize Next.js (TypeScript) web app
- [ ] Build day-wise itinerary display, map route view, and cost breakdown
- [ ] Add interactive user edit and replan triggers

### Phase 8: Testing & Evaluation
- [ ] Create benchmark test cases with varying constraint complexities
- [ ] Run comparative evaluation against single-agent baseline
- [ ] Measure constraint violation rate, schedule feasibility, and latency
- [ ] Finalize technical documentation and demo materials
