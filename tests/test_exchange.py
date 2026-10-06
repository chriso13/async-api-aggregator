import httpx
import pytest

from app.clients.base import APIError
from app.clients.exchange import get_exchange_rate

RATE_OK = {"amount": 1.0, "base": "USD", "date": "2026-10-02", "rates": {"EUR": 0.85}}


async def test_get_exchange_rate_success(make_client):
    def handler(request):
        assert request.url.params["from"] == "USD"
        assert request.url.params["to"] == "EUR"
        return httpx.Response(200, json=RATE_OK)

    result = await get_exchange_rate(make_client(handler), "usd", "eur")

    assert result.base == "USD"
    assert result.target == "EUR"
    assert result.rate == 0.85
    assert result.date == "2026-10-02"


async def test_get_exchange_rate_invalid_json(make_client):
    def handler(request):
        return httpx.Response(200, text="<html>Service temporarily down</html>")

    with pytest.raises(APIError, match="invalid JSON"):
        await get_exchange_rate(make_client(handler), "USD", "EUR")


async def test_get_exchange_rate_missing_rate(make_client):
    def handler(request):
        return httpx.Response(200, json={"base": "USD", "rates": {}})

    with pytest.raises(APIError, match="missing"):
        await get_exchange_rate(make_client(handler), "USD", "EUR")


async def test_get_exchange_rate_invalid_rate_value(make_client):
    def handler(request):
        return httpx.Response(200, json={"base": "USD", "rates": {"EUR": "abc"}})

    with pytest.raises(APIError, match="invalid rate"):
        await get_exchange_rate(make_client(handler), "USD", "EUR")


async def test_client_error_is_not_retried(make_client):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"message": "not found"})

    with pytest.raises(APIError, match="HTTP 404"):
        await get_exchange_rate(make_client(handler), "USD", "XYZ")
    assert calls == 1


async def test_same_currency_skips_api_call(make_client):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    result = await get_exchange_rate(make_client(handler), "USD", "USD")
    assert result.rate == 1.0
    assert calls == 0
