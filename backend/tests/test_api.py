"""
API integration tests using FastAPI TestClient.
Tests that require Gemini are marked with @pytest.mark.llm and skipped by default.
Run with: pytest -m llm  to include them.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import UserProfile, Traveler, Money, ProfileExtractionResult


client = TestClient(app)


# ─────────────── Mock helpers ───────────────

def _mock_profile(**overrides) -> UserProfile:
    defaults = dict(
        destination="Goa",
        origin="Mumbai",
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=33),
        budget=Money(amount=150000, currency="INR"),
        travelers=[
            Traveler(id="t1", age_group="adult", gender="male"),
            Traveler(id="t2", age_group="adult", gender="female"),
        ],
        interests=["beaches", "seafood"],
        hard_constraints={"max_daily_travel_hours": 2},
        soft_preferences={"prefer_window_seat": 0.8},
        missing_fields=[],
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def _mock_extraction_result(**profile_overrides) -> ProfileExtractionResult:
    profile = _mock_profile(**profile_overrides)
    return ProfileExtractionResult(
        profile=profile,
        is_complete=profile.is_complete,
        clarification_questions=[],
        request_id="test-request-id",
    )


# ──────────────────── Basic endpoint tests ───────────────────────────

class TestHealthEndpoints:
    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["message"] == "Welcome to Agentic Trip Planner API"

    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


# ──────────────────── Profile extract endpoint (mocked) ──────────────

class TestExtractEndpoint:
    @patch("app.api.endpoints.profile.extract_profile")
    def test_extract_returns_complete_profile(self, mock_extract):
        mock_extract.return_value = _mock_extraction_result()

        r = client.post("/api/profile/extract", json={
            "request_text": "Trip to Goa for 4 days"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_complete"] is True
        assert data["profile"]["destination"] == "Goa"
        assert data["request_id"] == "test-request-id"

    @patch("app.api.endpoints.profile.extract_profile")
    def test_extract_returns_incomplete_with_questions(self, mock_extract):
        mock_extract.return_value = ProfileExtractionResult(
            profile=_mock_profile(missing_fields=["budget"]),
            is_complete=False,
            clarification_questions=["What is your budget?"],
            request_id="test-incomplete",
        )

        r = client.post("/api/profile/extract", json={
            "request_text": "Trip to Goa"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_complete"] is False
        assert len(data["clarification_questions"]) == 1

    def test_extract_empty_text_returns_400(self):
        r = client.post("/api/profile/extract", json={"request_text": ""})
        assert r.status_code == 400

    def test_extract_missing_body_returns_422(self):
        r = client.post("/api/profile/extract", json={})
        assert r.status_code == 422


# ──────────────────── Profile clarify endpoint (mocked) ──────────────

class TestClarifyEndpoint:
    @patch("app.api.endpoints.profile.clarify_profile")
    def test_clarify_merges_followup(self, mock_clarify):
        mock_clarify.return_value = _mock_extraction_result()

        r = client.post("/api/profile/clarify", json={
            "request_id": "abc-123",
            "original_request": "Trip to Goa",
            "follow_up": "Budget is 1.5 lakhs, 2 adults",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_complete"] is True

    def test_clarify_empty_followup_returns_400(self):
        r = client.post("/api/profile/clarify", json={
            "request_id": "abc",
            "original_request": "Trip",
            "follow_up": "   ",
        })
        assert r.status_code == 400


# ──────────────────── POI Search Endpoint ───────────────────────────

class TestPOISearchEndpoint:
    def test_search_pois_success(self):
        profile_data = {
            "destination": "Goa",
            "start_date": (date.today() + timedelta(days=10)).isoformat(),
            "end_date": (date.today() + timedelta(days=14)).isoformat(),
            "budget": {"amount": 50000.0, "currency": "INR"},
            "travelers": [{"id": "t1", "age_group": "adult", "gender": "male", "accessibility_needs": []}],
            "interests": ["beaches", "seafood"],
            "hard_constraints": {},
            "soft_preferences": {},
            "missing_fields": []
        }
        r = client.post("/api/poi/search", json=profile_data)
        assert r.status_code == 200
        candidates = r.json()
        assert isinstance(candidates, list)
        assert len(candidates) > 0
        # Check candidate structure
        first = candidates[0]
        assert "id" in first
        assert "name" in first
        assert "coordinates" in first
        assert "category" in first
        assert "relevance_score" in first
        assert "evidence" in first


# ──────────────────── Route Agent Endpoints ─────────────────────────

class TestRouteEndpoints:
    def _sample_candidates(self):
        return [
            {
                "id": "p1",
                "name": "Baga Beach",
                "coordinates": [15.5523, 73.7516],
                "category": "Beach",
                "description": "Popular beach",
                "opening_hours": {"open_247": True},
                "visit_duration": 180,
                "cost_range": [0.0, 500.0],
                "accessibility": {"wheelchair_accessible": False},
                "evidence": {
                    "source_id": "seed",
                    "source_type": "internal_db",
                    "retrieved_at": "2026-10-11T00:00:00Z"
                },
                "relevance_score": 1.0
            },
            {
                "id": "p2",
                "name": "Basilica of Bom Jesus",
                "coordinates": [15.5009, 73.9116],
                "category": "Historic Site",
                "description": "Historic church",
                "opening_hours": {"monday": "09:00-18:00"},
                "visit_duration": 90,
                "cost_range": [0.0, 0.0],
                "accessibility": {"wheelchair_accessible": True},
                "evidence": {
                    "source_id": "seed",
                    "source_type": "internal_db",
                    "retrieved_at": "2026-10-11T00:00:00Z"
                },
                "relevance_score": 1.0
            }
        ]

    def test_route_matrix_success(self):
        candidates = self._sample_candidates()
        r = client.post("/api/route/matrix", json={"pois": candidates, "mode": "driving"})
        assert r.status_code == 200
        data = r.json()
        assert "distances" in data
        assert "travel_times" in data
        assert "p1:p2" in data["distances"]
        assert data["distances"]["p1:p2"] > 0
        assert data["mode"]["mode"] == "driving"

    def test_route_matrix_empty_fails(self):
        r = client.post("/api/route/matrix", json={"pois": []})
        assert r.status_code == 400

    def test_route_optimize_success(self):
        candidates = self._sample_candidates()
        r = client.post("/api/route/optimize", json={"candidates": candidates, "num_days": 1, "mode": "driving"})
        assert r.status_code == 200
        data = r.json()
        assert "daily_sequences" in data
        assert len(data["daily_sequences"]) == 1
        assert len(data["daily_sequences"][0]["ordered_poi_ids"]) == 2
        assert data["total_distance_meters"] > 0

    def test_route_optimize_empty_fails(self):
        r = client.post("/api/route/optimize", json={"candidates": [], "num_days": 1})
        assert r.status_code == 400


# ──────────────────── Constraint Agent Endpoints ────────────────────

class TestConstraintEndpoints:
    def _sample_payload(self):
        return {
            "profile": {
                "destination": "Goa",
                "start_date": "2026-11-01",
                "end_date": "2026-11-03",
                "budget": {"amount": 50000.0, "currency": "INR"},
                "travelers": [{"id": "t1", "age_group": "adult", "gender": "male", "accessibility_needs": []}],
                "interests": ["beaches"],
                "hard_constraints": {},
                "soft_preferences": {},
                "missing_fields": []
            },
            "candidates": [
                {
                    "id": "p1",
                    "name": "Baga Beach",
                    "coordinates": [15.5523, 73.7516],
                    "category": "Beach",
                    "description": "Popular beach",
                    "opening_hours": {"open_247": True},
                    "visit_duration": 180,
                    "cost_range": [0.0, 500.0],
                    "accessibility": {"wheelchair_accessible": True},
                    "evidence": {
                        "source_id": "seed",
                        "source_type": "internal_db",
                        "retrieved_at": "2026-10-11T00:00:00Z"
                    },
                    "relevance_score": 1.0
                }
            ]
        }

    def test_constraints_validate_success(self):
        payload = self._sample_payload()
        r = client.post("/api/constraints/validate", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "passed" in data
        assert data["passed"] is True
        assert "violations" in data

    def test_constraints_budget_breakdown(self):
        payload = self._sample_payload()
        r = client.post("/api/constraints/budget", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["total_budget"] == 50000.0
        assert data["within_budget"] is True
        assert "activities_min" in data
        assert "estimated_total_min" in data

    def test_constraints_validate_empty_fails(self):
        payload = self._sample_payload()
        payload["candidates"] = []
        r = client.post("/api/constraints/validate", json=payload)
        assert r.status_code == 400


# ──────────────────── Live Gemini tests (opt-in) ─────────────────────

@pytest.mark.llm
class TestLiveGeminiExtraction:
    """
    These tests call the real Gemini API.
    Run with:  pytest -m llm
    Skip with: pytest -m "not llm" (default)
    """

    @pytest.fixture(autouse=True)
    def check_api_key(self):
        key = os.getenv("GOOGLE_API_KEY", "")
        if not key or key == "your_google_api_key_here":
            pytest.skip("GOOGLE_API_KEY not set")

    def test_complete_family_trip(self):
        r = client.post("/api/profile/extract", json={
            "request_text": (
                "I want to plan a family trip to Goa for 4 days starting next month "
                "on the 10th. We are 2 adults (male and female) and 1 senior (female, "
                "needs wheelchair assistance). Our budget is 1,50,000 INR. We love "
                "beaches, seafood, and historic Portuguese churches."
            )
        })
        assert r.status_code == 200
        data = r.json()
        assert data["profile"]["destination"].lower() == "goa"
        assert len(data["profile"]["travelers"]) == 3
        assert data["profile"]["budget"]["amount"] == 150000

    def test_incomplete_request_flags_missing(self):
        r = client.post("/api/profile/extract", json={
            "request_text": "I want to go somewhere nice for a vacation"
        })
        assert r.status_code == 200
        data = r.json()
        # Should flag missing fields — destination is vague
        assert len(data["profile"]["missing_fields"]) > 0 or not data["is_complete"]
