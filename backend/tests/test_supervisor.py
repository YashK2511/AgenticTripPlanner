import pytest
from datetime import date
from app.models.schemas import TripPlanRequest, UserProfile, Money, Traveler
from app.orchestration.supervisor import run_trip_planner
from app.core.database import SessionLocal
from app.models.db_models import TripStateModel, AgentTraceModel
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestSupervisorWorkflow:
    def test_end_to_end_trip_planning_complete_profile(self):
        profile = UserProfile(
            destination="Goa",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
            budget=Money(amount=100000, currency="INR"),
            travelers=[Traveler(id="t1", age_group="adult", gender="male", accessibility_needs=[])],
            interests=["beaches", "seafood"],
            hard_constraints={},
            soft_preferences={},
            missing_fields=[],
        )

        req = TripPlanRequest(user_profile=profile)
        db = SessionLocal()
        try:
            response = run_trip_planner(request=req, db=db)
        finally:
            db.close()

        assert response.status == "completed"
        assert response.trip_id is not None
        assert response.profile is not None
        assert response.profile.destination == "Goa"
        assert len(response.candidates) > 0
        assert response.routes is not None
        assert len(response.routes.daily_sequences) > 0
        assert response.constraints is not None
        assert response.context is not None
        assert len(response.traces) >= 5

        # Verify trace nodes were executed
        node_names = {t.node_name for t in response.traces}
        assert {"profile_extract", "poi_retrieval", "context_fetch", "route_optimize", "constraint_check", "persist_state"}.issubset(node_names)

    def test_supervisor_incomplete_profile_routes_early(self):
        req = TripPlanRequest(request_text="I want to go somewhere nice for a vacation")
        db = SessionLocal()
        try:
            response = run_trip_planner(request=req, db=db)
        finally:
            db.close()

        assert response.status == "incomplete_profile"
        assert response.profile is not None
        assert not response.profile.is_complete
        assert len(response.clarification_questions) > 0
        assert len(response.candidates) == 0
        assert response.routes is None

        # Verify heavy nodes were skipped, only extract and persist ran
        node_names = {t.node_name for t in response.traces}
        assert "profile_extract" in node_names
        assert "persist_state" in node_names
        assert "poi_retrieval" not in node_names

    def test_database_persistence_of_trip_state_and_traces(self):
        profile = UserProfile(
            destination="Manali",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 4),
            budget=Money(amount=150000, currency="INR"),
            travelers=[Traveler(id="t1", age_group="adult", gender="female", accessibility_needs=[])],
            interests=["snow", "mountains"],
            hard_constraints={},
            soft_preferences={},
            missing_fields=[],
        )

        req = TripPlanRequest(user_profile=profile)
        db = SessionLocal()
        try:
            response = run_trip_planner(request=req, db=db)
            trip_id = response.trip_id

            # Verify in DB
            db_trip = db.query(TripStateModel).filter(TripStateModel.id == trip_id).first()
            assert db_trip is not None
            assert db_trip.profile_json["destination"] == "Manali"
            assert db_trip.candidates_json is not None
            assert db_trip.routes_json is not None
            assert db_trip.context_json is not None

            db_traces = db.query(AgentTraceModel).filter(AgentTraceModel.trip_id == trip_id).all()
            assert len(db_traces) >= 5
        finally:
            db.close()


class TestPlanAPIEndpoints:
    def test_api_plan_start_and_get(self):
        payload = {
            "user_profile": {
                "destination": "Goa",
                "start_date": "2026-11-01",
                "end_date": "2026-11-03",
                "budget": {"amount": 75000.0, "currency": "INR"},
                "travelers": [{"id": "t1", "age_group": "adult", "gender": "male", "accessibility_needs": []}],
                "interests": ["beaches"],
                "hard_constraints": {},
                "soft_preferences": {},
                "missing_fields": []
            },
            "mode": "driving"
        }

        # 1. Start plan
        r_start = client.post("/api/plan/start", json=payload)
        assert r_start.status_code == 200
        data = r_start.json()
        assert data["status"] == "completed"
        trip_id = data["trip_id"]

        # 2. Get plan by ID
        r_get = client.get(f"/api/plan/{trip_id}")
        assert r_get.status_code == 200
        get_data = r_get.json()
        assert get_data["trip_id"] == trip_id
        assert get_data["profile"]["destination"] == "Goa"
        assert len(get_data["candidates"]) > 0
        assert len(get_data["traces"]) >= 5

    def test_api_plan_not_found(self):
        r = client.get("/api/plan/nonexistent_trip_id_999")
        assert r.status_code == 404

    def test_api_plan_start_empty_fails(self):
        r = client.post("/api/plan/start", json={})
        assert r.status_code == 422
