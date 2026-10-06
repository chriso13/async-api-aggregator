"""Weather client using open-meteo (No api key needed)"""

from __future__ import annotations
import logging
import httpx
from app.clients.base import APIError, fetch_json
from app.config import settings
from app.models.response import WeatherResult

logger = logging.getLogger(__name__)

API_NAME = "weather"

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}

async def get_weather(
        client: httpx.AsyncClient, city: str, units: str = "fahrenheit"
) -> WeatherResult:
    logger.info("Calling weather API (city=%s)",city)
    geo = await fetch_json(
        client,
        settings.geocoding_url,
        api_name=API_NAME,
        params= {"name": city, "count": 1, "language": "en", "format": "json"}
    )

    results = geo.get("results") if isinstance(geo,dict) else None
    if not results :
        logger.warning("Weather API not found location matching %r", city)
        raise APIError(API_NAME, f"city '{city}' not found")
    try:
        location = results[0]
        latitude, longitude = location["latitude"], location["longitude"]
        resolved_city = location["name"]
    except(KeyError, TypeError, IndexError) as error:
        raise APIError(API_NAME, "invalid geocoding response") from error

    forecast = await fetch_json(
        client,
        settings.forecast_url,
        api_name= API_NAME,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "temperature_unit": units,
        },
    )

    try:
        current = forecast["current"]
        temperature = current["temperature_2m"]
        code = current["weather_code"]
    except (KeyError, TypeError) as error:
        logger.error("Weather API response is missing current weather data")
        raise APIError(API_NAME, "missing current weather data") from error

    if temperature is None:
        raise APIError(API_NAME, "temperature from response")

    return WeatherResult(
        city= resolved_city,
        temperature=temperature,
        condition=WEATHER_CODES.get(code, f"Ubknown (code {code})"),
        units="F" if units == "fahrenheit" else "C"
    )
    