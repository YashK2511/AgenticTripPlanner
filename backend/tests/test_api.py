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
