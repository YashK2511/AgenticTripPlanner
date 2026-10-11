import logging
from typing import List, Optional, Dict, Any
from app.models.schemas import (
    UserProfile,
    POICandidate,
    RouteOptimizationResult,
    ConstraintCheck,
    Violation,
    BudgetBreakdown,
)

logger = logging.getLogger("trip_planner.agents.constraint")

# Default daily travel & activity ceiling (10 hours = 600 minutes)
DEFAULT_MAX_DAILY_HOURS = 10.0


def compute_budget_breakdown(
    profile: UserProfile,
    candidates: List[POICandidate],
    estimated_transit_per_day: float = 1000.0,
) -> BudgetBreakdown:
    """
    Computes an itemized breakdown of estimated trip costs against the user's budget.
    """
    num_travelers = max(1, len(profile.travelers))
    trip_duration_days = max(1, (profile.end_date - profile.start_date).days + 1)

    # Activity costs scale by number of travelers for ticketing
    activities_min = sum(poi.cost_range[0] for poi in candidates) * num_travelers
    activities_max = sum(poi.cost_range[1] for poi in candidates) * num_travelers

    # Transit estimate across days
    estimated_transit = estimated_transit_per_day * trip_duration_days

    estimated_total_min = activities_min + estimated_transit
    estimated_total_max = activities_max + estimated_transit

    within_budget = estimated_total_min <= profile.budget.amount
    budget_margin_min = round(profile.budget.amount - estimated_total_min, 2)

    return BudgetBreakdown(
        total_budget=profile.budget.amount,
        currency=profile.budget.currency,
        activities_min=round(activities_min, 2),
        activities_max=round(activities_max, 2),
        estimated_transit=round(estimated_transit, 2),
        estimated_total_min=round(estimated_total_min, 2),
        estimated_total_max=round(estimated_total_max, 2),
        within_budget=within_budget,
        budget_margin_min=budget_margin_min,
    )


def _check_budget_constraints(
    profile: UserProfile,
    candidates: List[POICandidate],
) -> List[Violation]:
    """
    Validates total expenditure against user budget.
    """
    violations: List[Violation] = []
    breakdown = compute_budget_breakdown(profile, candidates)

    if not breakdown.within_budget:
        violations.append(
            Violation(
                type="budget",
                severity="hard",
                affected_item="total_trip_budget",
                reason=(
                    f"Estimated minimum trip cost (₹{breakdown.estimated_total_min:,.0f}) "
                    f"exceeds user budget ceiling (₹{profile.budget.amount:,.0f}) "
                    f"by ₹{abs(breakdown.budget_margin_min):,.0f}."
                ),
                repair_suggestion=(
                    "Remove luxury activities or paid venues, replace with free alternatives, "
                    "or increase the total trip budget."
                ),
            )
        )
    elif breakdown.estimated_total_max > profile.budget.amount:
        # Soft warning when upper bound could exceed budget
        violations.append(
            Violation(
                type="budget",
                severity="soft",
                affected_item="total_trip_budget",
                reason=(
                    f"Upper bound estimated trip cost (₹{breakdown.estimated_total_max:,.0f}) "
                    f"may exceed budget (₹{profile.budget.amount:,.0f})."
                ),
                repair_suggestion="Monitor on-site optional expenses and dining costs.",
            )
        )

    # Check explicit hard constraints if defined
    if "max_budget" in profile.hard_constraints:
        max_b = float(profile.hard_constraints["max_budget"])
        if breakdown.estimated_total_min > max_b:
            violations.append(
                Violation(
                    type="budget",
                    severity="hard",
                    affected_item="hard_constraints.max_budget",
                    reason=f"Estimated minimum cost exceeds hard constraint max_budget ₹{max_b:,.0f}.",
                    repair_suggestion="Trim candidate POI list to reduce mandatory costs.",
                )
            )

    return violations


def _check_accessibility_constraints(
    profile: UserProfile,
    candidates: List[POICandidate],
) -> List[Violation]:
    """
    Ensures POIs accommodate traveler accessibility requirements (e.g. wheelchairs, mobility).
    """
    violations: List[Violation] = []

    # Gather all traveler accessibility requirements
    required_needs = set()
    for traveler in profile.travelers:
        for need in traveler.accessibility_needs:
            cleaned = need.strip().lower()
            if cleaned:
                required_needs.add(cleaned)

    # Also check hard constraints for accessibility
    for key, val in profile.hard_constraints.items():
        if "wheelchair" in key.lower() or "accessibility" in key.lower():
            if val is True or str(val).lower() in ("true", "yes", "required"):
                required_needs.add("wheelchair")

    wheelchair_needed = any(
        "wheelchair" in need or "mobility" in need for need in required_needs
    )

    for poi in candidates:
        access_info = poi.accessibility or {}

        # 1. Wheelchair check
        if wheelchair_needed:
            is_accessible = access_info.get("wheelchair_accessible")
            if is_accessible is False:
                violations.append(
                    Violation(
                        type="accessibility",
                        severity="hard",
                        affected_item=poi.name,
                        reason=(
                            f"{poi.name} is not wheelchair accessible, violating "
                            f"mobility requirements for traveler(s)."
                        ),
                        repair_suggestion=(
                            f"Replace {poi.name} with an accessible venue or confirm on-site assistance."
                        ),
                    )
                )

        # 2. Heavy hiking / stairs check for seniors or mobility limitations
        has_seniors = any(t.age_group.lower() == "senior" for t in profile.travelers)
        if (wheelchair_needed or has_seniors) and access_info.get("requires_hiking"):
            violations.append(
                Violation(
                    type="accessibility",
                    severity="hard",
                    affected_item=poi.name,
                    reason=f"{poi.name} requires intensive hiking, which conflicts with traveler physical capabilities.",
                    repair_suggestion=f"Replace {poi.name} with an easy-access sightseeing venue.",
                )
            )

        if wheelchair_needed and access_info.get("stairs_present") and not access_info.get("elevators"):
            violations.append(
                Violation(
                    type="accessibility",
                    severity="soft",
                    affected_item=poi.name,
                    reason=f"{poi.name} has stairs and lacks elevators.",
                    repair_suggestion=f"Verify ramp access or ground-floor exhibits for {poi.name}.",
                )
            )

    return violations


def _check_opening_hours_constraints(
    candidates: List[POICandidate],
) -> List[Violation]:
    """
    Checks if any candidates are closed or have prohibitive operating schedules.
    """
    violations: List[Violation] = []

    for poi in candidates:
        hours = poi.opening_hours or {}

        if hours.get("closed") is True or hours.get("permanently_closed") is True:
            violations.append(
                Violation(
                    type="closed",
                    severity="hard",
                    affected_item=poi.name,
                    reason=f"{poi.name} is marked as closed.",
                    repair_suggestion=f"Remove {poi.name} from the itinerary.",
                )
            )

        # Check for season-locked venues
        if hours.get("season_only") and not hours.get("open_now", True):
            violations.append(
                Violation(
                    type="closed",
                    severity="hard",
                    affected_item=poi.name,
                    reason=f"{poi.name} is seasonally closed during this period.",
                    repair_suggestion=f"Replace {poi.name} with an all-season attraction.",
                )
            )

    return violations


def _check_schedule_time_constraints(
    candidates: List[POICandidate],
    route_result: Optional[RouteOptimizationResult],
    max_daily_hours: float = DEFAULT_MAX_DAILY_HOURS,
) -> List[Violation]:
    """
    Checks if daily schedules exceed maximum recommended travel + activity hours.
    """
    violations: List[Violation] = []
    if not route_result or not route_result.daily_sequences:
        return violations

    poi_map = {p.id: p for p in candidates}
    max_daily_minutes = max_daily_hours * 60.0

    for day_seq in route_result.daily_sequences:
        activity_minutes = sum(
            poi_map[pid].visit_duration for pid in day_seq.ordered_poi_ids if pid in poi_map
        )
        travel_minutes = day_seq.total_travel_time_minutes
        total_day_minutes = activity_minutes + travel_minutes

        if total_day_minutes > max_daily_minutes:
            severity = "hard" if total_day_minutes > (max_daily_minutes * 1.25) else "soft"
            violations.append(
                Violation(
                    type="time",
                    severity=severity,
                    affected_item=f"Day {day_seq.day} Schedule",
                    reason=(
                        f"Day {day_seq.day} scheduled time ({total_day_minutes / 60:.1f} hrs: "
                        f"{activity_minutes / 60:.1f} hrs activities + {travel_minutes / 60:.1f} hrs transit) "
                        f"exceeds max recommended daily ceiling ({max_daily_hours:.1f} hrs)."
                    ),
                    repair_suggestion=(
                        f"Move one venue from Day {day_seq.day} to another day or reduce visit durations."
                    ),
                )
            )

    return violations


def validate_constraints(
    profile: UserProfile,
    candidates: List[POICandidate],
    route_result: Optional[RouteOptimizationResult] = None,
    max_daily_hours: float = DEFAULT_MAX_DAILY_HOURS,
) -> ConstraintCheck:
    """
    Runs deterministic verification across all operational constraints:
    1. Budget limits & ceilings
    2. Traveler accessibility
    3. Opening hours & availability
    4. Daily time bounds
    """
    logger.info(
        "Validating constraints for destination=%s, budget=₹%s, candidates=%d",
        profile.destination, profile.budget.amount, len(candidates),
    )

    violations: List[Violation] = []

    # 1. Budget checks
    violations.extend(_check_budget_constraints(profile, candidates))

    # 2. Accessibility checks
    violations.extend(_check_accessibility_constraints(profile, candidates))

    # 3. Opening hours checks
    violations.extend(_check_opening_hours_constraints(candidates))

    # 4. Schedule time bounds checks
    violations.extend(
        _check_schedule_time_constraints(candidates, route_result, max_daily_hours)
    )

    # Check passes if there are NO hard violations
    hard_violations = [v for v in violations if v.severity == "hard"]
    passed = len(hard_violations) == 0

    logger.info(
        "Constraint check complete: passed=%s (hard violations=%d, soft violations=%d)",
        passed, len(hard_violations), len(violations) - len(hard_violations),
    )

    return ConstraintCheck(
        passed=passed,
        violations=violations,
    )
