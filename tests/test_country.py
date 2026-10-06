import dataclasses

import httpx
import pytest

import app.clients.base as base_module
import app.clients.country as country_module
from app.clients.base import APIError
from app.clients.country import get_country

TEST_KEY = "test-key"

US_OBJECT = {
    "names": {"common": "United States"},
    "capitals": [
        {"name": "Washington, D.C.", "attributes": {"primary": True}},
    ],
    "population": 331002651,
    "currencies": {"USD": {"name": "United States dollar", "symbol": "$"}},
}


def v5_ok(*objects):
    return {"data": {"objects": list(objects), "meta": {"total": len(objects), "count": len(objects)}}}


V5_EMPTY = v5_ok()


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    """Settings is frozen, so swap in a modified copy instead of mutating it."""
    patched = dataclasses.replace(
        country_module.settings,
        country_api_key=TEST_KEY,
        country_url="https://api.test/countries/v5",
        retry_backoff=0,  # keep retry tests fast
        max_retries=3,
    )
    monkeypatch.setattr(country_module, "settings", patched)
    monkeypatch.setattr(base_module, "settings", patched)
    return patched


async def test_get_country_success(make_client):
    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {TEST_KEY}"
        assert request.url.path in (
            "/countries/v5/names.common/United%20States",
            "/countries/v5/names.common/United States",
        )
        assert "names.common" in request.url.params["response_fields"]
        return httpx.Response(200, json=v5_ok(US_OBJECT))

    result = await get_country(make_client(handler), "United States")

    assert result.name == "United States"
    assert result.capital == "Washington, D.C."
    assert result.population == 331002651
    assert result.currency == "USD"


async def test_get_country_picks_primary_capital(make_client):
    multi = {
        **US_OBJECT,
        "names": {"common": "South Africa"},
        "capitals": [
            {"name": "Bloemfontein", "attributes": {"judicial": True}},
            {"name": "Pretoria", "attributes": {"executive": True, "primary": True}},
        ],
    }

    def handler(request):
        return httpx.Response(200, json=v5_ok(multi))

    result = await get_country(make_client(handler), "South Africa")
    assert result.capital == "Pretoria"


async def test_get_country_falls_back_to_name_search(make_client):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if "/names.common/" in request.url.path:
            return httpx.Response(200, json=V5_EMPTY)
        assert request.url.path.endswith("/name")
        assert request.url.params["q"] == "United"
        return httpx.Response(200, json=v5_ok(US_OBJECT))

    result = await get_country(make_client(handler), "United")

    assert result.name == "United States"
    assert len(paths) == 2


async def test_get_country_not_found(make_client):
    def handler(request):
        return httpx.Response(200, json=V5_EMPTY)

    with pytest.raises(APIError, match="country 'Narnia' not found"):
        await get_country(make_client(handler), "Narnia")


async def test_get_country_api_failure_retries(make_client):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with pytest.raises(APIError, match="unavailable after 3 attempts"):
        await get_country(make_client(handler), "United States")
    assert calls == 3


async def test_get_country_bad_key_surfaces_message(make_client):
    def handler(request):
        return httpx.Response(401, json={"errors": [{"message": "Invalid API key."}]})

    with pytest.raises(APIError, match=r"HTTP 401 \(Invalid API key\.\)"):
        await get_country(make_client(handler), "United States")


async def test_get_country_error_payload_on_200(make_client):
    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "Something went wrong"}]})

    with pytest.raises(APIError, match="Something went wrong"):
        await get_country(make_client(handler), "United States")


async def test_get_country_missing_api_key(make_client, monkeypatch, test_settings):
    no_key = dataclasses.replace(test_settings, country_api_key="")
    monkeypatch.setattr(country_module, "settings", no_key)

    def handler(request):
        raise AssertionError("should not make a request without a key")

    with pytest.raises(APIError, match="COUNTRY_API_KEY is not configured"):
        await get_country(make_client(handler), "United States")


async def test_get_country_missing_optional_fields(make_client):
    def handler(request):
        return httpx.Response(200, json=v5_ok({"names": {"common": "Antarctica"}, "population": 1000}))

    result = await get_country(make_client(handler), "Antarctica")

    assert result.name == "Antarctica"
    assert result.capital is None
    assert result.currency is None