import uuid
import logging
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.models.schemas import ContextData, WeatherInfo, Disruption

logger = logging.getLogger("trip_planner.agents.context")

# Severe condition keywords that trigger a disruption record
_SEVERE_KEYWORDS = (
    "storm", "cyclone", "typhoon", "hurricane", "tornado", "flood",
    "blizzard", "warning", "alert", "severe", "extreme", "evacuation",
    "monsoon warning", "heavy rain alert", "gale", "thunder",
)

_WEATHER_API_BASE = "https://api.weatherapi.com/v1"
_REQUEST_TIMEOUT = 4.0  # seconds


def _fallback_context() -> ContextData:
    return ContextData(
        weather=None,
        traffic=None,
        disruptions=[],
        availability={"weather": False, "traffic": False},
        retrieved_at=datetime.now(timezone.utc),
    )


def _parse_weather_response(destination: str, data: dict) -> tuple[WeatherInfo, list[Disruption]]:
    """
    Parse weatherapi.com JSON to WeatherInfo and any disruption records.
    Falls back gracefully on missing or unexpected keys.
    """
    current = data.get("current", {})
    condition_text = current.get("condition", {}).get("text", "Unknown")

    weather = WeatherInfo(
        destination=destination,
        condition=condition_text,
        temperature_c=current.get("temp_c"),
        feels_like_c=current.get("feelslike_c"),
        precipitation_chance=current.get("precip_mm", 0.0),
        humidity=current.get("humidity"),
        wind_speed_kmh=current.get("wind_kph"),
        forecast_days=[
            {
                "date": day.get("date"),
                "avgtemp_c": day.get("day", {}).get("avgtemp_c"),
                "condition": day.get("day", {}).get("condition", {}).get("text"),
                "daily_chance_of_rain": day.get("day", {}).get("daily_chance_of_rain"),
            }
            for day in data.get("forecast", {}).get("forecastday", [])
        ],
        warnings=[],
    )

    # Generate disruptions for severe weather conditions
    disruptions: list[Disruption] = []
    alerts = data.get("alerts", {}).get("alert", [])

    for alert in alerts:
        headline = alert.get("headline", "")
        description = alert.get("desc", headline)
        weather.warnings.append(headline)

        disruptions.append(
            Disruption(
                id=str(uuid.uuid4()),
                category="weather",
                severity="high",
                description=description,
                affected_area=destination,
            )
        )

    # Also check the condition text itself for severe keywords
    if not disruptions:
        lower_condition = condition_text.lower()
        if any(kw in lower_condition for kw in _SEVERE_KEYWORDS):
            disruptions.append(
                Disruption(
                    id=str(uuid.uuid4()),
                    category="weather",
                    severity="medium",
                    description=f"Potentially challenging weather conditions at {destination}: {condition_text}",
                    affected_area=destination,
                )
            )

    return weather, disruptions


def fetch_context(
    destination: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    api_key: Optional[str] = None,
) -> ContextData:
    """
    Fetches weather & disruption context for the destination over the trip dates.

    Graceful degradation:
    - No API key       → immediate fallback with availability["weather"] = False
    - Network error    → logged warning, fallback
    - Non-200 response → logged warning, fallback
    - JSON parse error → logged warning, fallback

    Uses weatherapi.com's forecast endpoint when available.
    """
    key = api_key or settings.WEATHER_API_KEY

    if not key or key.strip() == "":
        logger.info(
            "WEATHER_API_KEY not set. Returning fallback context for %s", destination
        )
        return _fallback_context()

    # Determine forecast days count (max 10 supported by free tier)
    if start_date and end_date:
        days = min(max((end_date - start_date).days + 1, 1), 10)
    else:
        days = 3  # sensible default

    url = f"{_WEATHER_API_BASE}/forecast.json"
    params = {
        "key": key,
        "q": destination,
        "days": days,
        "alerts": "yes",
        "aqi": "no",
    }

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.get(url, params=params)

        if response.status_code != 200:
            logger.warning(
                "Weather API returned non-200 status %d for %s. Falling back.",
                response.status_code, destination,
            )
            return _fallback_context()

        data = response.json()
        weather, disruptions = _parse_weather_response(destination, data)

        return ContextData(
            weather=weather,
            traffic=None,
            disruptions=disruptions,
            availability={"weather": True, "traffic": False},
            retrieved_at=datetime.now(timezone.utc),
        )

    except httpx.RequestError as exc:
        logger.warning(
            "Network error fetching weather context for %s: %s. Falling back.",
            destination, exc,
        )
        return _fallback_context()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Unexpected error in context_agent for %s: %s. Falling back.",
            destination, exc,
        )
        return _fallback_context()
