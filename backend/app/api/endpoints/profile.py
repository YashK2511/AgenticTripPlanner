import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.schemas import ProfileExtractionResult, ClarificationRequest
from app.agents.profile_agent import extract_profile, clarify_profile

logger = logging.getLogger("trip_planner.api.profile")

router = APIRouter()


class ProfileRequest(BaseModel):
    request_text: str


@router.post("/extract", response_model=ProfileExtractionResult)
def extract_user_profile(req: ProfileRequest):
    """
    Takes a natural language travel request and returns a structured UserProfile
    with completeness status and clarification questions if needed.
    """
    if not req.request_text.strip():
        raise HTTPException(status_code=400, detail="request_text cannot be empty")

    try:
        result = extract_profile(req.request_text)
        logger.info("Profile extraction completed, request_id=%s", result.request_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Profile extraction failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clarify", response_model=ProfileExtractionResult)
def clarify_user_profile(req: ClarificationRequest):
    """
    Takes a previous extraction's context plus the user's follow-up answer,
    and returns an updated profile with merged information.
    """
    if not req.follow_up.strip():
        raise HTTPException(status_code=400, detail="follow_up cannot be empty")

    try:
        result = clarify_profile(
            original_request=req.original_request,
            follow_up=req.follow_up,
            partial_profile=req.partial_profile,
        )
        logger.info("Profile clarification completed, request_id=%s", result.request_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Profile clarification failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
