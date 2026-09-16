from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.schemas import UserProfile
from app.agents.profile_agent import extract_profile

router = APIRouter()

class ProfileRequest(BaseModel):
    request_text: str

@router.post("/extract", response_model=UserProfile)
def extract_user_profile(req: ProfileRequest):
    """
    Takes a natural language travel request and returns a structured UserProfile.
    """
    try:
        profile = extract_profile(req.request_text)
        return profile
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
