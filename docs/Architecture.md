# System Architecture

## Overview
The architecture is structured as a Multi-Agent System (MAS) orchestrated by a central Supervisor Agent. It utilizes Retrieval-Augmented Generation (RAG) to ground recommendations in real data and uses specialized logical agents for deterministic tasks.

## Agent Roles
1. **Supervisor/Orchestrator Agent**: Manages state, assigns subtasks, tracks dependencies, handles conflicts and replanning.
2. **User Profile & Preference Agent**: Extracts structured profiles (hard constraints vs soft preferences) from natural language.
3. **Destination & POI Retrieval Agent**: Fetches candidates (POIs, hotels, restaurants) and filters them.
4. **Transportation & Route Planning Agent**: Calculates travel times, distances, and proposes visit orders.
5. **Budget & Constraint Agent**: Checks budget, opening windows, accessibility, and time constraints.
6. **Context Agent**: Checks weather, traffic (when available).
7. **Itinerary Synthesis Agent**: Assembles validated data into coherent day-wise blocks with rationale.
8. **Critic/Verification Agent**: Independently verifies the final plan against constraints (hallucinations, duplicates, time overlaps) before release.

## Data Flow
- Natural Language Input -> Supervisor 
- Supervisor -> Profile Agent (Structured Constraints)
- Supervisor -> Retrieval Agents (Data Gathering)
- Supervisor -> Route & Budget Agents (Feasibility Checks)
- Supervisor -> Synthesis Agent (Draft Assembly)
- Synthesis -> Critic Agent (Validation)
- Critic -> (Pass? Output Itinerary : Fail? Return to Supervisor for Replanning)

## Technology Stack
- **Frontend**: React / Next.js (TypeScript)
- **Backend**: FastAPI (Python 3.x), LangGraph (Agent Orchestration)
- **Database**: PostgreSQL with pgvector (Embeddings/State)
- **APIs/Libraries**: OR-Tools, NetworkX, sentence-transformers, LLM API
