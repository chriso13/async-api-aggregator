import httpx
import pytest

from app.clients.base import APIError
from app.clients.weather import get_weather

GEOCODING_HOST = "geocoding-api.open-meteo.com"
FORECAST_HOST = "api.open-meteo.com"

GEO_OK = {"results": [{"name": "Miami", "latitude": 25.77, "longitude": -80.19}]}
FORECAST_OK = {"current": {"temperature_2m": 84.2, "weather_code": 0}}


def ok_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == GEOCODING_HOST:
        return httpx.Response(200, json=GEO_OK)
    if request.url.host == FORECAST_HOST:
        # Guards against the earlier bugs: a space in the variable list and a misspelled param.
        assert request.url.params["current"] == "temperature_2m,weather_code"
        assert request.url.params["temperature_unit"] in ("fahrenheit", "celsius")
        return httpx.Response(200, json=FORECAST_OK)
    return httpx.Response(404)


async def test_get_weather_success(make_client):
    result = await get_weather(make_client(ok_handler), "Miami")

    assert result.city == "Miami"
    assert result.temperature == 84.2
    assert result.condition == "Clear sky"
    assert result.units == "F"


async def test_get_weather_celsius(make_client):
    seen_units = []

    def handler(request):
        if request.url.host == FORECAST_HOST:
            seen_units.append(request.url.params["temperature_unit"])
        return ok_handler(request)

    result = await get_weather(make_client(handler), "Miami", units="celsius")
    assert result.units == "C"
    assert seen_units == ["celsius"]


async def test_get_weather_bad_request_surfaces_reason(make_client):
    def handler(request):
        if request.url.host == GEOCODING_HOST:
            return httpx.Response(200, json=GEO_OK)
        return httpx.Response(400, json={"error": True, "reason": "Cannot initialize WeatherVariable"})

    with pytest.raises(APIError, match=r"HTTP 400 \(Cannot initialize WeatherVariable\)"):
        await get_weather(make_client(handler), "Miami")


async def test_get_weather_api_failure_retries_then_raises(make_client):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    with pytest.raises(APIError, match="unavailable after 3 attempts"):
        await get_weather(make_client(handler), "Miami")
    assert calls == 3


async def test_get_weather_retry_then_success(make_client):
    geo_attempts = 0

    def handler(request):
        nonlocal geo_attempts
        if request.url.host == GEOCODING_HOST:
            geo_attempts += 1
            if geo_attempts < 3:
                return httpx.Response(500)
        return ok_handler(request)

    result = await get_weather(make_client(handler), "Miami")
    assert result.city == "Miami"
    assert geo_attempts == 3


async def test_get_weather_timeout(make_client):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(APIError, match="timed out"):
        await get_weather(make_client(handler), "Miami")


async def test_get_weather_connection_error(make_client):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(APIError, match="connection error"):
        await get_weather(make_client(handler), "Miami")


async def test_get_weather_city_not_found(make_client):
    def handler(request):
        return httpx.Response(200, json={"generationtime_ms": 0.4})

    with pytest.raises(APIError, match="not found"):
        await get_weather(make_client(handler), "Atlantisville")


async def test_get_weather_missing_current_data(make_client):
    def handler(request):
        if request.url.host == GEOCODING_HOST:
            return httpx.Response(200, json=GEO_OK)
        return httpx.Response(200, json={"latitude": 25.77})

    with pytest.raises(APIError, match="missing current weather data"):
        await get_weather(make_client(handler), "Miami")
