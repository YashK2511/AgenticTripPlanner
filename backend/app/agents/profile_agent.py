import logging
import uuid
from datetime import date
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from app.models.schemas import UserProfile, ProfileExtractionResult

logger = logging.getLogger("trip_planner.agents.profile")

# ──────────────────────── Required fields for a complete profile ─────
REQUIRED_FIELDS = ["destination", "start_date", "end_date", "budget", "travelers"]


def get_llm():
    """
    Initialize Google Gemini LLM using centralized settings.
    """
    if not settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY environment variable not set")

    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        temperature=0,
        google_api_key=settings.GOOGLE_API_KEY,
    )


# ──────────────────────── Extraction prompt ──────────────────────────

PROFILE_EXTRACTION_SYSTEM_PROMPT = """You are an expert AI Travel Agent specializing in extracting structured travel profiles from natural language requests.
Your task is to analyze the user's travel request and extract the parameters into the specified schema.

Instructions:
1. Identify the destination and origin (if provided).
2. Extract the exact trip dates (start_date and end_date) in YYYY-MM-DD format. Assume current year if only month/day are given and it's logically in the future.
3. Extract the total budget in INR (Indian Rupees). Convert from other currencies if mentioned (e.g., $1 USD ≈ ₹83 INR).
4. Identify all travelers. Provide a unique ID for each traveler (e.g., 'traveler_1'). Determine their age_group (adult, child, senior), gender (male, female, other), and any accessibility_needs.
5. Extract a list of travel interests (e.g., 'museums', 'hiking', 'fine dining').
6. Extract 'hard_constraints': Conditions the trip MUST meet (e.g., 'must have wheelchair access', 'no flights longer than 5 hours', 'maximum budget ₹500000').
7. Extract 'soft_preferences': Things the user prefers but are negotiable. Assign a weight from 0.1 (low) to 1.0 (high) for each (e.g., {{'prefer window seat': 0.8}}).
8. If any crucial information is missing (like destination, dates, or budget), list them in 'missing_fields'.

Current Date Context: {current_date}

IMPORTANT: All monetary amounts must be in INR (Indian Rupees).
"""

# ──────────────────────── Clarification prompt ───────────────────────

CLARIFICATION_SYSTEM_PROMPT = """You are an expert AI Travel Agent. A user previously submitted a travel request but some information was missing or unclear.
Their original request and a follow-up response are provided below. Merge the follow-up information with the original request to produce a COMPLETE travel profile.

Rules:
1. If the follow-up provides missing fields (like destination, dates, budget), fill them in.
2. Do NOT discard information from the original request — only add or update.
3. If crucial fields are STILL missing after merging, list them in 'missing_fields'.
4. Dates must be in YYYY-MM-DD format. Budget must be in INR.
5. Keep all existing travelers, interests, constraints, and preferences unless the follow-up explicitly changes them.

Current Date Context: {current_date}
"""


def _generate_clarification_questions(profile: UserProfile) -> List[str]:
    """
    Generate human-readable clarification questions based on missing_fields.
    """
    question_map = {
        "destination": "Where would you like to travel to?",
        "start_date": "When would you like to start your trip? (Please specify a date)",
        "end_date": "When should the trip end? (Or how many days should it be?)",
        "budget": "What is your total budget for this trip (in INR)?",
        "travelers": "Who will be traveling? (Number of people, ages, any special needs?)",
        "origin": "Where will you be traveling from?",
        "interests": "What activities or experiences are you interested in?",
    }

    questions = []
    for field in profile.missing_fields:
        q = question_map.get(field)
        if q:
            questions.append(q)
        else:
            questions.append(f"Could you provide more details about: {field}?")
    return questions


def _validate_profile(profile: UserProfile) -> UserProfile:
    """
    Run deterministic validation on extracted profile and populate missing_fields
    if the LLM missed flagging them.
    """
    missing = list(profile.missing_fields)  # start with what the LLM detected

    # Check destination is not a placeholder
    if not profile.destination or profile.destination.lower() in ("unknown", "tbd", "not specified"):
        if "destination" not in missing:
            missing.append("destination")

    # Check budget is positive
    if profile.budget.amount <= 0:
        if "budget" not in missing:
            missing.append("budget")

    # Check travelers list is non-empty
    if not profile.travelers:
        if "travelers" not in missing:
            missing.append("travelers")

    # Check dates are not in the past
    today = date.today()
    if profile.start_date < today:
        logger.warning("start_date %s is in the past", profile.start_date)

    profile.missing_fields = missing
    return profile


def extract_profile(user_request: str) -> ProfileExtractionResult:
    """
    Extracts a UserProfile from a natural language travel request.
    Returns a ProfileExtractionResult with completeness info and clarification questions.
    """
    logger.info("Extracting profile from user request (%d chars)", len(user_request))

    prompt = ChatPromptTemplate.from_messages([
        ("system", PROFILE_EXTRACTION_SYSTEM_PROMPT),
        ("human", "Travel Request: {request}")
    ])

    llm = get_llm()
    structured_llm = llm.with_structured_output(UserProfile)
    chain = prompt | structured_llm

    current_date = date.today().isoformat()

    result = chain.invoke({
        "current_date": current_date,
        "request": user_request,
    })

    # Run deterministic validation on top of LLM output
    result = _validate_profile(result)

    request_id = str(uuid.uuid4())
    questions = _generate_clarification_questions(result)

    logger.info(
        "Profile extracted: destination=%s, travelers=%d, complete=%s, request_id=%s",
        result.destination, len(result.travelers), result.is_complete, request_id,
    )

    return ProfileExtractionResult(
        profile=result,
        is_complete=result.is_complete,
        clarification_questions=questions,
        request_id=request_id,
    )


def clarify_profile(
    original_request: str,
    follow_up: str,
    partial_profile: UserProfile | None = None,
) -> ProfileExtractionResult:
    """
    Takes the original request + user's follow-up answer and returns an updated profile.
    """
    logger.info("Clarifying profile with follow-up (%d chars)", len(follow_up))

    context_parts = [f"Original Request: {original_request}"]
    if partial_profile:
        context_parts.append(f"Previously Extracted Profile:\n{partial_profile.model_dump_json(indent=2)}")
    context_parts.append(f"User's Follow-Up: {follow_up}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", CLARIFICATION_SYSTEM_PROMPT),
        ("human", "\n\n".join(context_parts)),
    ])

    llm = get_llm()
    structured_llm = llm.with_structured_output(UserProfile)
    chain = prompt | structured_llm

    current_date = date.today().isoformat()
    result = chain.invoke({"current_date": current_date})

    result = _validate_profile(result)

    request_id = str(uuid.uuid4())
    questions = _generate_clarification_questions(result)

    logger.info(
        "Clarified profile: destination=%s, complete=%s, request_id=%s",
        result.destination, result.is_complete, request_id,
    )

    return ProfileExtractionResult(
        profile=result,
        is_complete=result.is_complete,
        clarification_questions=questions,
        request_id=request_id,
    )
