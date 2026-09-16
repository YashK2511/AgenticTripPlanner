import logging
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from app.models.schemas import UserProfile

logger = logging.getLogger("trip_planner.agents.profile")


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


def extract_profile(user_request: str) -> UserProfile:
    """
    Extracts a UserProfile from a natural language travel request.
    """
    logger.info("Extracting profile from user request (%d chars)", len(user_request))

    prompt = ChatPromptTemplate.from_messages([
        ("system", PROFILE_EXTRACTION_SYSTEM_PROMPT),
        ("human", "Travel Request: {request}")
    ])

    llm = get_llm()

    # We use LangChain's built-in structured output parsing
    structured_llm = llm.with_structured_output(UserProfile)

    # Create the chain
    chain = prompt | structured_llm

    from datetime import date
    current_date = date.today().isoformat()

    # Execute the chain
    result = chain.invoke({
        "current_date": current_date,
        "request": user_request
    })

    logger.info("Profile extracted: destination=%s, travelers=%d", result.destination, len(result.travelers))
    return result
