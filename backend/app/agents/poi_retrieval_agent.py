import logging
from typing import List, Tuple
from sqlalchemy.orm import Session

from app.models.db_models import POICandidateModel, POIEmbeddingModel
from app.models.schemas import UserProfile, POICandidate, Evidence
from app.services.embedding_service import encode_text, cosine_similarity

logger = logging.getLogger("trip_planner.agents.poi_retrieval")


def retrieve_pois(profile: UserProfile, db: Session, top_k: int = 10) -> List[POICandidate]:
    """
    Agentic retrieval pipeline for finding POIs that match the user's profile.
    Uses semantic vector search combined with hard constraint filtering.

    Args:
        profile: The extracted UserProfile.
        db: SQLAlchemy database session.
        top_k: Number of results to return.

    Returns:
        List of semantically matched and filtered POICandidates.
    """
    logger.info("Starting POI retrieval for destination: %s", profile.destination)

    # 1. Synthesize the semantic query
    query_parts = [f"Best places to visit in {profile.destination}"]
    if profile.interests:
        query_parts.append(f"Specifically looking for: {', '.join(profile.interests)}")

    # Incorporate soft preferences if any
    for pref, weight in profile.soft_preferences.items():
        if weight > 0.6:  # Only add high-weight preferences to the query text
            query_parts.append(pref)

    query_text = ". ".join(query_parts)
    logger.debug("Synthesized query: %s", query_text)

    # 2. Encode the query
    query_vector = encode_text(query_text)

    # 3. Load candidates (In PostgreSQL/pgvector, this would be an exact SQL ANN query.
    #    Here we fetch candidates matching the destination and calculate in memory).
    #
    # We do a loose text match on description (which we seeded with the city name).
    city_ilike = f"%{profile.destination}%"

    db_candidates = db.query(POICandidateModel, POIEmbeddingModel)\
        .join(POIEmbeddingModel, POICandidateModel.id == POIEmbeddingModel.poi_id)\
        .filter(POICandidateModel.description.ilike(city_ilike))\
        .all()

    if not db_candidates:
        logger.warning("No POIs found in database for city: %s", profile.destination)
        return []

    # 4. Score and filter candidates
    scored_candidates: List[Tuple[float, POICandidateModel]] = []

    # Extract constraints
    needs_wheelchair = False
    for t in profile.travelers:
        if "wheelchair" in " ".join(t.accessibility_needs).lower():
            needs_wheelchair = True

    # Allow custom hard constraints if specified, else False
    if profile.hard_constraints.get("wheelchair_accessible_only") is True:
        needs_wheelchair = True

    budget_limit = profile.budget.amount

    for poi_model, embed_model in db_candidates:
        # ----- Hard Filter Check -----
        # Wheelchair accessible?
        if needs_wheelchair and not poi_model.accessibility_json.get("wheelchair_accessible", False):
            continue

        # Budget Check (if a POI's minimum cost exceeds the TOTAL trip budget, exclude it immediately)
        if poi_model.cost_range_min is not None and poi_model.cost_range_min > budget_limit:
            continue

        # ----- Semantic Scoring -----
        sim_score = cosine_similarity(query_vector, embed_model.embedding_json)

        scored_candidates.append((sim_score, poi_model))

    # 5. Rank and map to Pydantic schemas
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    top_candidates = scored_candidates[:top_k]

    results = []
    for score, poi in top_candidates:
        # Convert Evidence JSON dict to Pydantic schema
        evidence = Evidence(**poi.evidence_json)

        candidate = POICandidate(
            id=poi.id,
            name=poi.name,
            coordinates=(poi.coordinates_lat, poi.coordinates_lng),
            category=poi.category,
            description=poi.description,
            opening_hours=poi.opening_hours_json or {},
            visit_duration=poi.visit_duration or 60,
            cost_range=(poi.cost_range_min or 0.0, poi.cost_range_max or 0.0),
            accessibility=poi.accessibility_json or {},
            evidence=evidence,
            relevance_score=float(score)
        )
        results.append(candidate)

    logger.info("Retrieved %d matching POIs.", len(results))
    return results
