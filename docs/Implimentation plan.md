# Implementation Plan

## Overview
This document outlines the step-by-step implementation strategy for the LLM-Orchestrated Multi-Agent Trip Planner.

## Phase Breakdown

### Phase 1: Environment & Project Foundation
- **Goal**: Set up developer environment, base schemas, and backend scaffolding.
- **Tasks**:
  1. Initialize Python 3.10+ virtual environment and dependencies (`fastapi`, `langgraph`, `pydantic`, `sqlalchemy`, `pgvector`, `sentence-transformers`).
  2. Setup PostgreSQL database with `pgvector` extension enabled.
  3. Create core Pydantic domain models for user profiles, POIs, constraints, and trip state.
  4. Build basic FastAPI skeleton with health check and CORS settings.

### Phase 2: User Profile & Constraint Extraction Agent
- **Goal**: Convert free-form user text into structured, typed constraints.
- **Tasks**:
  1. Implement prompt templates and LLM structured output parsing for user preferences.
  2. Differentiate between hard constraints (budget ceilings, accessibility, mandatory dates) and soft preferences (pace, specific cuisine).
  3. Implement missing-field detection and clarification generation logic.
  4. Write unit tests for extraction across edge cases (family trips, tight budgets, high mobility constraints).

### Phase 3: RAG & POI Retrieval Agent
- **Goal**: Semantic search, filtering, and grounding of venue/POI data.
- **Tasks**:
  1. Set up vector embeddings table in PostgreSQL for POIs, activities, restaurants, and stays.
  2. Implement semantic search using `sentence-transformers` and cosine similarity.
  3. Add metadata filters for city, price range, opening hours, and accessibility.
  4. Attach evidence provenance (source ID, timestamp, coordinate validity) to every retrieved candidate.

### Phase 4: Route Matrix & Budget Constraint Agents
- **Goal**: Calculate accurate travel metrics and enforce operational rules.
- **Tasks**:
  1. Implement Route Agent to calculate pairwise distance and travel times using a routing service (or local NetworkX/OSRM fallback).
  2. Add OR-Tools visit-order optimization heuristic to minimize detour distances.
  3. Implement Budget & Constraint Agent to compute cumulative costs and daily duration bounds.
  4. Emit machine-readable violation objects when constraints fail.

### Phase 5: Multi-Agent Orchestration & Shared State
- **Goal**: Supervisor workflow coordinating parallel and sequential agent tasks.
- **Tasks**:
  1. Implement the state graph using LangGraph to manage shared trip state.
  2. Define explicit task decomposition, execution triggers, and fallback handlers.
  3. Integrate Context Agent (weather/traffic conditions) with graceful degradation when APIs are missing.
  4. Ensure end-to-end provenance and trace logging for every agent action.

### Phase 6: Itinerary Synthesis & Critic Verification Agents
- **Goal**: Generate time-blocked day plans and perform independent adversarial checks.
- **Tasks**:
  1. Implement Synthesis Agent to assemble POIs, meals, transit, and rest periods into daily blocks.
  2. Implement Critic Agent to audit for hallucinations, time overlaps, venue closures, and budget breaches.
  3. Build the structured conflict reporting mechanism (`severity`, `affected_item`, `repair_action`).

### Phase 7: Automated Replanning & Interactive UI
- **Goal**: Handle conflict loops and build a web client.
- **Tasks**:
  1. Implement Supervisor replanning loop: invoke only affected agents based on Critic conflict reports.
  2. Build Next.js / React web interface with day-wise itinerary views, map overlays, and rationale cards.
  3. Add interactive editing allowing user-driven partial or full replans.

### Phase 8: Evaluation & Benchmark Comparison
- **Goal**: Assess feasibility, constraint compliance, and compare against baselines.
- **Tasks**:
  1. Build a test suite of representative travel queries with diverse constraints.
  2. Evaluate against a single-agent baseline and rule-based heuristic baseline.
  3. Track metrics: constraint violation rate, schedule feasibility, and response latency.
