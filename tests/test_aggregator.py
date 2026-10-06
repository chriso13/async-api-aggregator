import asyncio
import time

import pytest

from app import aggregator
from app.aggregator import aggregate, aggregate_sequential
from app.clients.base import APIError
from app.models.response import (
    AggregateRequest,
    CountryResult,
    ExchangeResult,
    WeatherResult,
)

REQUEST = AggregateRequest(
    city="Miami", base_currency="USD", target_currency="EUR", country="United States"
)
DELAY = 0.2  # simulated network latency per API

EXPECTED = {
    "weather": {"city": "Miami", "temperature": 84.0, "condition": "Sunny", "units": "F"},
    "exchange": {"base": "USD", "target": "EUR", "rate": 0.85, "date": "2026-10-02"},
    "country": {
        "name": "United States",
        "capital": "Washington, D.C.",
        "population": 331000000,
        "currency": "USD",
    },
}


@pytest.fixture
def fake_clients(monkeypatch):
    """Replace the real clients with fakes that just sleep and return data."""

    async def fake_weather(client, city, units="fahrenheit"):
        await asyncio.sleep(DELAY)
        return WeatherResult(
            city=city,
            temperature=84.0,
            condition="Sunny",
            units="F" if units == "fahrenheit" else "C",
        )

    async def fake_exchange(client, base, target):
        await asyncio.sleep(DELAY)
        return ExchangeResult(base=base, target=target, rate=0.85, date="2026-10-02")

    async def fake_country(client, name):
        await asyncio.sleep(DELAY)
        return CountryResult(
            name=name, capital="Washington, D.C.", population=331000000, currency="USD"
        )

    monkeypatch.setattr(aggregator, "get_weather", fake_weather)
    monkeypatch.setattr(aggregator, "get_exchange_rate", fake_exchange)
    monkeypatch.setattr(aggregator, "get_country", fake_country)


async def test_all_results_are_combined(fake_clients):
    result = await aggregate(REQUEST, client=None)
    assert result == EXPECTED


async def test_units_are_passed_through(fake_clients):
    request = AggregateRequest(
        city="Miami", base_currency="USD", target_currency="EUR", units="celsius"
    )
    result = await aggregate(request, client=None)
    assert result["weather"]["units"] == "C"


async def test_one_api_failure_is_handled(monkeypatch, fake_clients):
    async def broken_exchange(*args, **kwargs):
        raise APIError("exchange", "HTTP 503")

    monkeypatch.setattr(aggregator, "get_exchange_rate", broken_exchange)

    result = await aggregate(REQUEST, client=None)

    assert result["exchange"] == {"error": "Exchange API unavailable: HTTP 503"}
    assert result["weather"] == EXPECTED["weather"]
    assert result["country"] == EXPECTED["country"]


async def test_unexpected_exception_is_handled(monkeypatch, fake_clients):
    async def buggy_country(*args, **kwargs):
        raise RuntimeError("bug in client")

    monkeypatch.setattr(aggregator, "get_country", buggy_country)

    result = await aggregate(REQUEST, client=None)

    assert result["country"] == {"error": "Country API failed unexpectedly"}
    assert result["weather"] == EXPECTED["weather"]
    assert result["exchange"] == EXPECTED["exchange"]


async def test_all_apis_failing_returns_only_errors(monkeypatch, fake_clients):
    async def down(*args, **kwargs):
        raise APIError("any", "HTTP 503")

    for name in ("get_weather", "get_exchange_rate", "get_country"):
        monkeypatch.setattr(aggregator, name, down)

    result = await aggregate(REQUEST, client=None)

    assert set(result) == {"weather", "exchange", "country"}
    assert all("error" in section for section in result.values())


async def test_sequential_mode_handles_failures_the_same_way(monkeypatch, fake_clients):
    async def broken_exchange(*args, **kwargs):
        raise APIError("exchange", "HTTP 503")

    monkeypatch.setattr(aggregator, "get_exchange_rate", broken_exchange)

    concurrent_result = await aggregate(REQUEST, client=None)
    sequential_result = await aggregate_sequential(REQUEST, client=None)

    assert concurrent_result == sequential_result


async def test_country_is_skipped_when_not_requested(fake_clients):
    request = AggregateRequest(city="Miami", base_currency="USD", target_currency="EUR")
    result = await aggregate(request, client=None)
    assert set(result) == {"weather", "exchange"}


async def test_concurrent_is_faster_than_sequential(fake_clients):
    start = time.perf_counter()
    concurrent_result = await aggregate(REQUEST, client=None)
    concurrent_time = time.perf_counter() - start

    start = time.perf_counter()
    sequential_result = await aggregate_sequential(REQUEST, client=None)
    sequential_time = time.perf_counter() - start

    assert concurrent_result == sequential_result == EXPECTED
    assert concurrent_time < DELAY * 2   # ~0.2s: all three overlap
    assert sequential_time >= DELAY * 3  # ~0.6s: one after another