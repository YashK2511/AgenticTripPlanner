import pytest
from datetime import datetime, timezone
from app.agents.route_agent import (
    compute_haversine_distance,
    estimate_travel_time,
    compute_route_matrix,
    solve_visit_sequence,
    EARTH_RADIUS_METERS,
)
from app.models.schemas import POICandidate, Evidence


def _make_poi(id: str, name: str, lat: float, lng: float, duration: int = 60) -> POICandidate:
    return POICandidate(
        id=id,
        name=name,
        coordinates=(lat, lng),
        category="Sightseeing",
        description=f"Description for {name}",
        opening_hours={"monday": "09:00-18:00"},
        visit_duration=duration,
        cost_range=(0.0, 100.0),
        accessibility={"wheelchair_accessible": True},
        evidence=Evidence(
            source_id="test",
            source_type="internal_db",
            retrieved_at=datetime.now(timezone.utc),
        ),
        relevance_score=1.0,
    )


class TestHaversineAndTravelTimes:
    def test_same_coordinates_zero_distance(self):
        coord = (15.5523, 73.7516)
        dist = compute_haversine_distance(coord, coord)
        assert dist == 0.0

    def test_known_coordinates_distance(self):
        # Baga Beach -> Basilica of Bom Jesus (~18-24 km depending on detour factor)
        baga = (15.5523, 73.7516)
        basilica = (15.5009, 73.9116)
        straight_line = compute_haversine_distance(baga, basilica, apply_road_detour=False)
        with_detour = compute_haversine_distance(baga, basilica, apply_road_detour=True)

        assert 15000 < straight_line < 22000
        assert with_detour == round(straight_line * 1.25, 2)

    def test_travel_time_proportional_to_speed(self):
        dist = 35000.0  # 35 km
        driving_time = estimate_travel_time(dist, mode="driving")
        walking_time = estimate_travel_time(dist, mode="walking")
        transit_time = estimate_travel_time(dist, mode="transit")

        # Driving at 35 km/h should take ~60 minutes
        assert 55 <= driving_time <= 65
        # Walking at 4.5 km/h should take much longer than driving
        assert walking_time > driving_time * 6
        # Transit at 25 km/h should be between driving and walking
        assert driving_time < transit_time < walking_time

    def test_zero_distance_zero_time(self):
        assert estimate_travel_time(0.0, mode="driving") == 0.0


class TestRouteMatrix:
    def test_empty_pois_matrix(self):
        matrix = compute_route_matrix([], mode="driving")
        assert len(matrix.distances) == 0
        assert len(matrix.travel_times) == 0

    def test_pairwise_matrix_generation(self):
        p1 = _make_poi("p1", "Place 1", 15.5, 73.7)
        p2 = _make_poi("p2", "Place 2", 15.6, 73.8)
        p3 = _make_poi("p3", "Place 3", 15.7, 73.9)

        matrix = compute_route_matrix([p1, p2, p3], mode="driving")

        assert len(matrix.distances) == 9
        assert len(matrix.travel_times) == 9

        # Diagonal entries must be 0
        assert matrix.get_distance("p1", "p1") == 0.0
        assert matrix.get_travel_time("p2", "p2") == 0.0

        # Off-diagonal entries must be strictly positive
        assert matrix.get_distance("p1", "p2") > 0
        assert matrix.get_travel_time("p1", "p2") > 0

        # Matrix should be symmetric
        assert matrix.get_distance("p1", "p2") == matrix.get_distance("p2", "p1")


class TestVisitSequencing:
    def test_empty_pois_optimization(self):
        matrix = compute_route_matrix([], mode="driving")
        result = solve_visit_sequence([], matrix, num_days=1)
        assert len(result.daily_sequences) == 0
        assert result.total_distance_meters == 0.0

    def test_single_poi_optimization(self):
        p1 = _make_poi("p1", "Place 1", 15.5, 73.7)
        matrix = compute_route_matrix([p1], mode="driving")
        result = solve_visit_sequence([p1], matrix, num_days=1)

        assert len(result.daily_sequences) == 1
        assert result.daily_sequences[0].ordered_poi_ids == ["p1"]
        assert result.daily_sequences[0].total_distance_meters == 0.0

    def test_multi_poi_single_day_tsp(self):
        p1 = _make_poi("p1", "Place 1", 15.5, 73.7)
        p2 = _make_poi("p2", "Place 2", 15.6, 73.8)
        p3 = _make_poi("p3", "Place 3", 15.7, 73.9)

        pois = [p1, p2, p3]
        matrix = compute_route_matrix(pois, mode="driving")
        result = solve_visit_sequence(pois, matrix, num_days=1)

        assert len(result.daily_sequences) == 1
        day1 = result.daily_sequences[0]
        assert set(day1.ordered_poi_ids) == {"p1", "p2", "p3"}
        assert len(day1.ordered_poi_ids) == 3
        assert day1.total_distance_meters > 0
        assert day1.total_travel_time_minutes > 0

    def test_multi_day_partitioning(self):
        # 4 POIs spread over 2 days
        pois = [
            _make_poi("p1", "North 1", 15.60, 73.75),
            _make_poi("p2", "North 2", 15.61, 73.76),
            _make_poi("p3", "South 1", 15.20, 73.90),
            _make_poi("p4", "South 2", 15.21, 73.91),
        ]
        matrix = compute_route_matrix(pois, mode="driving")
        result = solve_visit_sequence(pois, matrix, num_days=2)

        assert len(result.daily_sequences) == 2
        all_visited = []
        for ds in result.daily_sequences:
            all_visited.extend(ds.ordered_poi_ids)

        assert len(all_visited) == 4
        assert set(all_visited) == {"p1", "p2", "p3", "p4"}
        assert result.total_distance_meters > 0
