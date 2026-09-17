"""
Unit tests for profile validation and schema logic.
These tests do NOT call the Gemini API — they test the deterministic parts.
"""
import pytest
from datetime import date, timedelta
from app.models.schemas import UserProfile, Traveler, Money, ProfileExtractionResult
from app.agents.profile_agent import _validate_profile, _generate_clarification_questions


# ─────────────── Helpers ───────────────

def _make_profile(**overrides) -> UserProfile:
    """Build a valid UserProfile with sensible defaults, applying overrides."""
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


# ──────────────────── Schema validation tests ────────────────────────

class TestUserProfileSchema:
    def test_valid_profile_creates_successfully(self):
        p = _make_profile()
        assert p.destination == "Goa"
        assert len(p.travelers) == 2

    def test_trip_duration_days(self):
        p = _make_profile(
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 13),
        )
        assert p.trip_duration_days == 4

    def test_is_complete_when_no_missing_fields(self):
        p = _make_profile(missing_fields=[])
        assert p.is_complete is True

    def test_is_incomplete_when_fields_missing(self):
        p = _make_profile(missing_fields=["budget"])
        assert p.is_complete is False

    def test_end_date_before_start_date_raises(self):
        with pytest.raises(ValueError, match="end_date must be on or after start_date"):
            _make_profile(
                start_date=date(2026, 10, 15),
                end_date=date(2026, 10, 10),
            )

    def test_single_day_trip(self):
        d = date(2026, 10, 10)
        p = _make_profile(start_date=d, end_date=d)
        assert p.trip_duration_days == 1

    def test_traveler_accessibility_needs(self):
        p = _make_profile(
            travelers=[
                Traveler(id="t1", age_group="senior", gender="female",
                         accessibility_needs=["wheelchair"]),
            ]
        )
        assert p.travelers[0].accessibility_needs == ["wheelchair"]


# ──────────────────── Validation logic tests ─────────────────────────

class TestValidateProfile:
    def test_valid_profile_stays_valid(self):
        p = _make_profile()
        result = _validate_profile(p)
        assert result.missing_fields == []

    def test_placeholder_destination_flagged(self):
        p = _make_profile(destination="unknown")
        result = _validate_profile(p)
        assert "destination" in result.missing_fields

    def test_tbd_destination_flagged(self):
        p = _make_profile(destination="TBD")
        result = _validate_profile(p)
        assert "destination" in result.missing_fields

    def test_zero_budget_flagged(self):
        p = _make_profile(budget=Money(amount=0, currency="INR"))
        result = _validate_profile(p)
        assert "budget" in result.missing_fields

    def test_negative_budget_flagged(self):
        p = _make_profile(budget=Money(amount=-1000, currency="INR"))
        result = _validate_profile(p)
        assert "budget" in result.missing_fields

    def test_empty_travelers_flagged(self):
        p = _make_profile(travelers=[])
        result = _validate_profile(p)
        assert "travelers" in result.missing_fields

    def test_no_duplicate_missing_fields(self):
        """If the LLM already flagged a field, validation shouldn't double it."""
        p = _make_profile(destination="unknown", missing_fields=["destination"])
        result = _validate_profile(p)
        assert result.missing_fields.count("destination") == 1

    def test_valid_destination_not_flagged(self):
        p = _make_profile(destination="Manali")
        result = _validate_profile(p)
        assert "destination" not in result.missing_fields


# ──────────────────── Clarification question tests ───────────────────

class TestClarificationQuestions:
    def test_no_questions_when_complete(self):
        p = _make_profile(missing_fields=[])
        qs = _generate_clarification_questions(p)
        assert qs == []

    def test_question_for_destination(self):
        p = _make_profile(missing_fields=["destination"])
        qs = _generate_clarification_questions(p)
        assert len(qs) == 1
        assert "travel to" in qs[0].lower()

    def test_question_for_budget(self):
        p = _make_profile(missing_fields=["budget"])
        qs = _generate_clarification_questions(p)
        assert any("budget" in q.lower() for q in qs)

    def test_multiple_missing_fields(self):
        p = _make_profile(missing_fields=["destination", "budget", "travelers"])
        qs = _generate_clarification_questions(p)
        assert len(qs) == 3

    def test_unknown_field_gets_generic_question(self):
        p = _make_profile(missing_fields=["pet_policy"])
        qs = _generate_clarification_questions(p)
        assert len(qs) == 1
        assert "pet_policy" in qs[0]


# ──────────────────── ProfileExtractionResult tests ──────────────────

class TestProfileExtractionResult:
    def test_complete_result(self):
        p = _make_profile()
        r = ProfileExtractionResult(
            profile=p,
            is_complete=True,
            clarification_questions=[],
            request_id="abc-123",
        )
        assert r.is_complete is True
        assert r.request_id == "abc-123"

    def test_incomplete_result_with_questions(self):
        p = _make_profile(missing_fields=["budget"])
        r = ProfileExtractionResult(
            profile=p,
            is_complete=False,
            clarification_questions=["What is your budget?"],
            request_id="def-456",
        )
        assert r.is_complete is False
        assert len(r.clarification_questions) == 1
