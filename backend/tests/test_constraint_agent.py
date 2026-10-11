import pytest
from datetime import date, datetime, timezone
from app.agents.constraint_agent import (
    validate_constraints,
    compute_budget_breakdown,
)
from app.models.schemas import (
    UserProfile,
    Money,
    Traveler,
    POICandidate,
    Evidence,
    RouteOptimizationResult,
    RouteMatrix,
    TransportMode,
    VisitSequence,
)


def _make_poi(
    id: str,
    name: str,
    cost_range=(0.0, 100.0),
    visit_duration=60,
    accessibility=None,
    opening_hours=None,
) -> POICandidate:
    return POICandidate(
        id=id,
        name=name,
        coordinates=(15.5, 73.7),
        category="Sightseeing",
        description=f"Description for {name}",
        opening_hours=opening_hours or {"monday": "09:00-18:00"},
        visit_duration=visit_duration,
        cost_range=cost_range,
        accessibility=accessibility or {"wheelchair_accessible": True},
        evidence=Evidence(
            source_id="test",
            source_type="internal_db",
            retrieved_at=datetime.now(timezone.utc),
        ),
        relevance_score=1.0,
    )


def _make_profile(
    budget_amount=50000.0,
    travelers=None,
    hard_constraints=None,
) -> UserProfile:
    if travelers is None:
        travelers = [Traveler(id="t1", age_group="adult", gender="male", accessibility_needs=[])]
    return UserProfile(
        destination="Goa",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),  # 3 days
        budget=Money(amount=budget_amount, currency="INR"),
        travelers=travelers,
        interests=["beach", "history"],
        hard_constraints=hard_constraints or {},
        soft_preferences={"pace": 0.5},
        missing_fields=[],
    )


class TestBudgetConstraints:
    def test_within_budget_passes(self):
        prof = _make_profile(budget_amount=50000.0)
        p1 = _make_poi("p1", "Fort Aguada", cost_range=(50, 200))
        p2 = _make_poi("p2", "Baga Beach", cost_range=(0, 500))

        check = validate_constraints(prof, [p1, p2])
        assert check.passed is True
        assert len([v for v in check.violations if v.severity == "hard"]) == 0

    def test_budget_exceeded_fails_hard(self):
        prof = _make_profile(budget_amount=5000.0)
        # Luxury hotel or expensive venue exceeding ₹5,000
        p_expensive = _make_poi("p_exp", "Luxury Resort", cost_range=(20000, 30000))

        check = validate_constraints(prof, [p_expensive])
        assert check.passed is False
        hard_violations = [v for v in check.violations if v.severity == "hard"]
        assert len(hard_violations) >= 1
        budget_viol = hard_violations[0]
        assert budget_viol.type == "budget"
        assert "exceeds user budget" in budget_viol.reason
        assert budget_viol.repair_suggestion != ""

    def test_upper_bound_soft_warning(self):
        # Min cost + transit is 4,000 (within 5,000 budget), but max cost is 8,000 (exceeds budget)
        prof = _make_profile(budget_amount=5000.0)
        p = _make_poi("p", "Casino", cost_range=(1000, 7000))

        check = validate_constraints(prof, [p])
        # Should pass because min is within budget
        assert check.passed is True
        soft_budget = [v for v in check.violations if v.type == "budget" and v.severity == "soft"]
        assert len(soft_budget) == 1

    def test_explicit_hard_constraint_max_budget(self):
        prof = _make_profile(budget_amount=50000.0, hard_constraints={"max_budget": 5000.0})
        p = _make_poi("p", "Resort", cost_range=(6000, 10000))

        check = validate_constraints(prof, [p])
        assert check.passed is False
        assert any("max_budget" in v.affected_item for v in check.violations)

    def test_compute_budget_breakdown(self):
        prof = _make_profile(budget_amount=20000.0)
        p1 = _make_poi("p1", "P1", cost_range=(500, 1500))
        p2 = _make_poi("p2", "P2", cost_range=(1000, 2000))

        breakdown = compute_budget_breakdown(prof, [p1, p2])
        assert breakdown.total_budget == 20000.0
        assert breakdown.activities_min == 1500.0
        assert breakdown.activities_max == 3500.0
        assert breakdown.within_budget is True
        assert breakdown.budget_margin_min > 0


class TestAccessibilityConstraints:
    def test_wheelchair_inaccessible_fails_hard(self):
        prof = _make_profile(
            travelers=[
                Traveler(id="t1", age_group="adult", gender="female", accessibility_needs=["wheelchair user"])
            ]
        )
        p_inaccessible = _make_poi(
            "p1", "Rocky Cave", accessibility={"wheelchair_accessible": False}
        )

        check = validate_constraints(prof, [p_inaccessible])
        assert check.passed is False
        access_viols = [v for v in check.violations if v.type == "accessibility" and v.severity == "hard"]
        assert len(access_viols) >= 1
        assert "not wheelchair accessible" in access_viols[0].reason

    def test_wheelchair_accessible_passes(self):
        prof = _make_profile(
            travelers=[
                Traveler(id="t1", age_group="adult", gender="female", accessibility_needs=["wheelchair"])
            ]
        )
        p_accessible = _make_poi(
            "p1", "Modern Museum", accessibility={"wheelchair_accessible": True}
        )

        check = validate_constraints(prof, [p_accessible])
        assert check.passed is True

    def test_senior_hiking_conflict_fails(self):
        prof = _make_profile(
            travelers=[
                Traveler(id="t1", age_group="senior", gender="male", accessibility_needs=[])
            ]
        )
        p_trek = _make_poi(
            "p_trek", "Mountain Trek", accessibility={"requires_hiking": True}
        )

        check = validate_constraints(prof, [p_trek])
        assert check.passed is False
        assert any(v.type == "accessibility" and "hiking" in v.reason for v in check.violations)

    def test_stairs_without_elevator_soft_warning(self):
        prof = _make_profile(
            travelers=[
                Traveler(id="t1", age_group="adult", gender="other", accessibility_needs=["wheelchair"])
            ]
        )
        p_stairs = _make_poi(
            "p_stairs", "Old Manor", accessibility={"wheelchair_accessible": True, "stairs_present": True, "elevators": False}
        )

        check = validate_constraints(prof, [p_stairs])
        assert check.passed is True
        soft_viols = [v for v in check.violations if v.type == "accessibility" and v.severity == "soft"]
        assert len(soft_viols) == 1


class TestOpeningHoursAndScheduleConstraints:
    def test_closed_venue_fails(self):
        prof = _make_profile()
        p_closed = _make_poi("p1", "Renovating Museum", opening_hours={"closed": True})

        check = validate_constraints(prof, [p_closed])
        assert check.passed is False
        assert any(v.type == "closed" and v.severity == "hard" for v in check.violations)

    def test_seasonally_closed_venue_fails(self):
        prof = _make_profile()
        p_snow = _make_poi("p1", "Snow Pass", opening_hours={"season_only": True, "open_now": False})

        check = validate_constraints(prof, [p_snow])
        assert check.passed is False
        assert any(v.type == "closed" for v in check.violations)

    def test_overloaded_day_schedule_fails_time_ceiling(self):
        prof = _make_profile()
        # 3 venues of 300 minutes (5 hours) each on a single day = 15 hours
        p1 = _make_poi("p1", "Venue 1", visit_duration=300)
        p2 = _make_poi("p2", "Venue 2", visit_duration=300)
        p3 = _make_poi("p3", "Venue 3", visit_duration=300)

        route_res = RouteOptimizationResult(
            matrix=RouteMatrix(distances={}, travel_times={}, mode=TransportMode(mode="driving")),
            daily_sequences=[
                VisitSequence(
                    day=1,
                    ordered_poi_ids=["p1", "p2", "p3"],
                    total_distance_meters=20000.0,
                    total_travel_time_minutes=60.0,
                )
            ],
            total_distance_meters=20000.0,
            total_travel_time_minutes=60.0,
        )

        check = validate_constraints(prof, [p1, p2, p3], route_result=route_res, max_daily_hours=10.0)
        # Total time is 15h activities + 1h transit = 16h > 12.5h (hard limit)
        assert check.passed is False
        assert any(v.type == "time" for v in check.violations)
