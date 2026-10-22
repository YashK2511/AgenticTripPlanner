import pytest
import httpx
from unittest.mock import patch, MagicMock
from datetime import date
from app.agents.context_agent import fetch_context
from app.models.schemas import ContextData


class TestContextAgent:
    def test_fetch_context_without_api_key_returns_fallback(self):
        context = fetch_context("Goa", api_key="")
        assert isinstance(context, ContextData)
        assert context.weather is None
        assert context.disruptions == []
        assert context.availability == {"weather": False, "traffic": False}

    @patch("httpx.Client.get")
    def test_fetch_context_success_with_weather(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current": {
                "temp_c": 30.5,
                "feelslike_c": 34.0,
                "humidity": 75.0,
                "wind_kph": 12.0,
                "condition": {"text": "Sunny"},
            },
            "forecast": {
                "forecastday": [
                    {
                        "date": "2026-11-01",
                        "day": {
                            "avgtemp_c": 29.0,
                            "condition": {"text": "Sunny"},
                            "daily_chance_of_rain": 10,
                        },
                    }
                ]
            },
            "alerts": {"alert": []},
        }
        mock_get.return_value = mock_response

        context = fetch_context(
            "Goa",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
            api_key="mock_key",
        )

        assert context.availability["weather"] is True
        assert context.weather is not None
        assert context.weather.destination == "Goa"
        assert context.weather.condition == "Sunny"
        assert context.weather.temperature_c == 30.5
        assert len(context.weather.forecast_days) == 1

    @patch("httpx.Client.get")
    def test_fetch_context_with_severe_weather_alert(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "current": {"temp_c": 25.0, "condition": {"text": "Heavy Rain"}},
            "forecast": {"forecastday": []},
            "alerts": {
                "alert": [
                    {
                        "headline": "Severe Cyclone Warning for Coastal Goa",
                        "desc": "Severe Cyclone Warning: High winds and heavy downpours expected.",
                    }
                ]
            },
        }
        mock_get.return_value = mock_response

        context = fetch_context("Goa", api_key="mock_key")

        assert context.availability["weather"] is True
        assert len(context.disruptions) == 1
        assert context.disruptions[0].category == "weather"
        assert context.disruptions[0].severity == "high"
        assert "Cyclone" in context.disruptions[0].description

    @patch("httpx.Client.get")
    def test_fetch_context_network_error_graceful_fallback(self, mock_get):
        mock_get.side_effect = httpx.ConnectTimeout("Connection timed out")

        context = fetch_context("Goa", api_key="mock_key")

        assert isinstance(context, ContextData)
        assert context.weather is None
        assert context.availability == {"weather": False, "traffic": False}

    @patch("httpx.Client.get")
    def test_fetch_context_non_200_status_graceful_fallback(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        context = fetch_context("Goa", api_key="invalid_key")

        assert context.availability == {"weather": False, "traffic": False}
        assert context.weather is None
