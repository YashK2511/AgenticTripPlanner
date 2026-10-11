import logging
import math
from typing import List, Tuple, Dict, Optional, Literal
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

from app.models.schemas import (
    POICandidate,
    TransportMode,
    RouteMatrix,
    VisitSequence,
    RouteOptimizationResult,
)

logger = logging.getLogger("trip_planner.agents.route")

EARTH_RADIUS_METERS = 6371000.0
ROAD_DETOUR_FACTOR = 1.25  # Approximates road distance over straight-line haversine

# Average urban speeds in meters per minute
SPEED_PROFILES: Dict[str, float] = {
    "walking": 4500.0 / 60.0,    # ~4.5 km/h = 75 m/min
    "bicycling": 15000.0 / 60.0, # ~15.0 km/h = 250 m/min
    "transit": 25000.0 / 60.0,   # ~25.0 km/h = 416.7 m/min
    "driving": 35000.0 / 60.0,   # ~35.0 km/h = 583.3 m/min
}


def compute_haversine_distance(
    coord1: Tuple[float, float],
    coord2: Tuple[float, float],
    apply_road_detour: bool = True,
) -> float:
    """
    Computes the great-circle distance in meters between two (lat, lng) pairs.
    Optionally applies a road network detour multiplier for realistic road routing.
    """
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    distance = EARTH_RADIUS_METERS * c

    if apply_road_detour:
        distance *= ROAD_DETOUR_FACTOR

    return round(distance, 2)


def estimate_travel_time(distance_meters: float, mode: str = "driving") -> float:
    """
    Estimates travel time in minutes based on distance and transport mode.
    """
    speed = SPEED_PROFILES.get(mode, SPEED_PROFILES["driving"])
    if distance_meters <= 0.0:
        return 0.0
    # Travel time in minutes
    return round(distance_meters / speed, 2)


def compute_route_matrix(
    pois: List[POICandidate],
    mode: Literal["walking", "transit", "driving", "bicycling"] = "driving",
) -> RouteMatrix:
    """
    Calculates pairwise distance (meters) and travel time (minutes) between all POIs.
    Produces stringified keys ("from_id:to_id") for JSON compatibility.
    """
    distances: Dict[str, float] = {}
    travel_times: Dict[str, float] = {}

    for i, poi_a in enumerate(pois):
        for j, poi_b in enumerate(pois):
            key = f"{poi_a.id}:{poi_b.id}"
            if poi_a.id == poi_b.id:
                distances[key] = 0.0
                travel_times[key] = 0.0
            else:
                dist = compute_haversine_distance(poi_a.coordinates, poi_b.coordinates)
                time_mins = estimate_travel_time(dist, mode)
                distances[key] = dist
                travel_times[key] = time_mins

    return RouteMatrix(
        distances=distances,
        travel_times=travel_times,
        mode=TransportMode(mode=mode),
    )


def _solve_single_day_tsp(
    pois: List[POICandidate],
    matrix: RouteMatrix,
) -> Tuple[List[str], float, float]:
    """
    Uses OR-Tools TSP solver to find optimal visit order for a single day.
    Returns (ordered_poi_ids, total_distance_meters, total_travel_time_minutes).
    """
    n = len(pois)
    if n == 0:
        return [], 0.0, 0.0
    if n == 1:
        return [pois[0].id], 0.0, 0.0
    if n == 2:
        poi_ids = [pois[0].id, pois[1].id]
        dist = matrix.get_distance(poi_ids[0], poi_ids[1])
        t_time = matrix.get_travel_time(poi_ids[0], poi_ids[1])
        return poi_ids, dist, t_time

    # Build cost matrix (scaled integers for OR-Tools)
    cost_matrix: List[List[int]] = []
    for i, p_from in enumerate(pois):
        row: List[int] = []
        for j, p_to in enumerate(pois):
            if i == j:
                row.append(0)
            else:
                # Use travel time in seconds as cost metric
                t_sec = int(matrix.get_travel_time(p_from.id, p_to.id) * 60)
                row.append(t_sec)
        cost_matrix.append(row)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return cost_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(transit_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 1

    solution = routing.SolveWithParameters(search_parameters)

    ordered_poi_ids: List[str] = []
    if solution:
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            ordered_poi_ids.append(pois[node].id)
            index = solution.Value(routing.NextVar(index))
    else:
        # Fallback to original order if solver fails
        logger.warning("OR-Tools TSP did not find solution; falling back to default order")
        ordered_poi_ids = [p.id for p in pois]

    # Calculate exact total distance and travel time along the route
    total_dist = 0.0
    total_time = 0.0
    for idx in range(len(ordered_poi_ids) - 1):
        from_id = ordered_poi_ids[idx]
        to_id = ordered_poi_ids[idx + 1]
        total_dist += matrix.get_distance(from_id, to_id)
        total_time += matrix.get_travel_time(from_id, to_id)

    return ordered_poi_ids, round(total_dist, 2), round(total_time, 2)


def _partition_pois_into_days(
    pois: List[POICandidate],
    num_days: int,
    matrix: RouteMatrix,
    max_hours_per_day: float = 8.0,
) -> List[List[POICandidate]]:
    """
    Partitions POIs across days using spatial-temporal proximity clustering.
    Ensures geographically close venues are clustered on the same day.
    """
    if not pois or num_days <= 1:
        return [pois] if pois else []

    if len(pois) <= num_days:
        # Fewer POIs than days: at most one POI per day
        return [[p] for p in pois]

    max_mins_per_day = max_hours_per_day * 60.0
    clusters: List[List[POICandidate]] = [[] for _ in range(num_days)]
    cluster_times: List[float] = [0.0 for _ in range(num_days)]

    # 1. Select seed POIs for each day that are spread apart
    unassigned = list(pois)
    seed = unassigned.pop(0)
    clusters[0].append(seed)
    cluster_times[0] += seed.visit_duration

    for day_idx in range(1, num_days):
        if not unassigned:
            break
        # Pick POI furthest from existing seeds
        best_poi = None
        max_min_dist = -1.0
        for cand in unassigned:
            min_dist_to_existing = min(
                compute_haversine_distance(cand.coordinates, s[0].coordinates)
                for s in clusters[:day_idx]
            )
            if min_dist_to_existing > max_min_dist:
                max_min_dist = min_dist_to_existing
                best_poi = cand
        if best_poi:
            unassigned.remove(best_poi)
            clusters[day_idx].append(best_poi)
            cluster_times[day_idx] += best_poi.visit_duration

    # 2. Greedily assign remaining POIs to the closest cluster that fits time budget
    for cand in unassigned:
        best_day = 0
        min_distance = float("inf")

        for d_idx in range(num_days):
            day_pois = clusters[d_idx]
            if not day_pois:
                best_day = d_idx
                min_distance = 0.0
                break

            # Distance to cluster centroid / closest POI in cluster
            d_to_cluster = min(
                matrix.get_distance(cand.id, existing.id) for existing in day_pois
            )
            est_new_time = cluster_times[d_idx] + cand.visit_duration + 30.0  # +30m transit est

            # Favor clusters with room under max daily hours
            penalty = 1.0 if est_new_time <= max_mins_per_day else 2.5
            effective_dist = d_to_cluster * penalty

            if effective_dist < min_distance:
                min_distance = effective_dist
                best_day = d_idx

        clusters[best_day].append(cand)
        cluster_times[best_day] += cand.visit_duration

    # Filter out any empty clusters
    return [c for c in clusters if c]


def solve_visit_sequence(
    pois: List[POICandidate],
    matrix: RouteMatrix,
    num_days: int = 1,
    max_hours_per_day: float = 8.0,
) -> RouteOptimizationResult:
    """
    Optimizes the multi-day visit schedule:
    1. Partitions POIs across days with geographic clustering.
    2. Runs OR-Tools TSP sequencing for each day.
    3. Aggregates distances, travel times, and ordered sequences.
    """
    if not pois:
        return RouteOptimizationResult(
            matrix=matrix,
            daily_sequences=[],
            total_distance_meters=0.0,
            total_travel_time_minutes=0.0,
        )

    day_clusters = _partition_pois_into_days(
        pois, num_days=num_days, matrix=matrix, max_hours_per_day=max_hours_per_day
    )

    daily_sequences: List[VisitSequence] = []
    grand_total_dist = 0.0
    grand_total_time = 0.0

    for day_num, day_pois in enumerate(day_clusters, start=1):
        ordered_ids, day_dist, day_time = _solve_single_day_tsp(day_pois, matrix)
        daily_sequences.append(
            VisitSequence(
                day=day_num,
                ordered_poi_ids=ordered_ids,
                total_distance_meters=day_dist,
                total_travel_time_minutes=day_time,
            )
        )
        grand_total_dist += day_dist
        grand_total_time += day_time

    return RouteOptimizationResult(
        matrix=matrix,
        daily_sequences=daily_sequences,
        total_distance_meters=round(grand_total_dist, 2),
        total_travel_time_minutes=round(grand_total_time, 2),
    )
