from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, JSON, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class TripStateModel(Base):
    """
    SQLAlchemy model for TripState - stores the overall state of a trip planning session.
    """
    __tablename__ = "trip_states"

    id = Column(String, primary_key=True, index=True)
    profile_json = Column(JSON, nullable=True)  # Serialized UserProfile
    candidates_json = Column(JSON, nullable=True)  # Dict of POICandidate
    routes_json = Column(JSON, nullable=True)  # Serialized RouteMatrix
    constraints_json = Column(JSON, nullable=True)  # Serialized ConstraintCheck
    context_json = Column(JSON, nullable=True)  # Serialized ContextData (Phase 5)
    itinerary_versions_json = Column(JSON, nullable=True)  # List of Itinerary
    current_version = Column(Integer, default=0)
    validation_status_json = Column(JSON, nullable=True)  # Serialized ValidationReport
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class UserProfileModel(Base):
    """
    SQLAlchemy model for storing user profiles independently.
    """
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_state_id = Column(String, index=True)  # FK to trip_states
    destination = Column(String, nullable=False)
    origin = Column(String, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    budget_amount = Column(Float, nullable=False)
    budget_currency = Column(String, default="INR")
    travelers_json = Column(JSON, nullable=False)  # List of Traveler dicts
    interests_json = Column(JSON, nullable=False)  # List of interest strings
    hard_constraints_json = Column(JSON, nullable=False)  # Dict
    soft_preferences_json = Column(JSON, nullable=False)  # Dict
    missing_fields_json = Column(JSON, nullable=False)  # List
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class POICandidateModel(Base):
    """
    SQLAlchemy model for POI candidates with vector embeddings.
    Will be extended with pgvector in Phase 3.
    """
    __tablename__ = "poi_candidates"

    id = Column(String, primary_key=True, index=True)
    trip_state_id = Column(String, index=True)
    name = Column(String, nullable=False)
    coordinates_lat = Column(Float, nullable=False)
    coordinates_lng = Column(Float, nullable=False)
    category = Column(String, index=True)
    description = Column(Text)
    opening_hours_json = Column(JSON)
    visit_duration = Column(Integer)  # minutes
    cost_range_min = Column(Float)
    cost_range_max = Column(Float)
    accessibility_json = Column(JSON)
    evidence_json = Column(JSON)  # Serialized Evidence
    relevance_score = Column(Float, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class POIEmbeddingModel(Base):
    """
    SQLAlchemy model for storing POI embeddings.
    For SQLite, we store as JSON arrays. For Postgres, this will be migrated to pgvector.
    """
    __tablename__ = "poi_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    poi_id = Column(String, index=True, unique=True, nullable=False)
    embedding_json = Column(JSON, nullable=False)  # List[float] representing 384-D vector
    model_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceModel(Base):
    """
    SQLAlchemy model for evidence metadata tracking.
    """
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    url = Column(String, nullable=True)
    poi_id = Column(String, index=True)  # FK to poi_candidates
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentTraceModel(Base):
    """
    SQLAlchemy model for storing per-node execution telemetry during LangGraph supervisor runs.
    """
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String, nullable=False, index=True)
    trace_id = Column(String, nullable=False, index=True)
    agent_name = Column(String, nullable=False)
    node_name = Column(String, nullable=False)
    status = Column(String, nullable=False)  # "success" | "failure" | "skipped" | "error"
    latency_ms = Column(Float, nullable=False)
    input_summary_json = Column(JSON, nullable=True)
    output_summary_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
