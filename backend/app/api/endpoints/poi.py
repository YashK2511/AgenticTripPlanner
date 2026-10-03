import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import UserProfile, POICandidate
from app.agents.poi_retrieval_agent import retrieve_pois

logger = logging.getLogger("trip_planner.api.poi")

router = APIRouter()


@router.post("/search", response_model=List[POICandidate])
def search_pois(profile: UserProfile, db: Session = Depends(get_db)):
    """
    Search for Point of Interest candidates based on the structured UserProfile.
    Uses semantic vector search and hard constraint filtering (e.g., budget, accessibility).
    """
    try:
        logger.info(
            "Searching POIs for destination=%s, travelers=%d",
            profile.destination, len(profile.travelers)
        )
        candidates = retrieve_pois(profile=profile, db=db, top_k=10)
        return candidates
    except Exception as e:
        logger.error("POI search failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
