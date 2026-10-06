from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.clients.base import APIError, fetch_json
from app.config import settings
from app.models.response import CountryResult

logger = logging.getLogger(__name__)

API_NAME = "country"
FIELDS = "names.common,capitals,population,currencies"


def _objects(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise APIError(API_NAME, "unexpected response format")
    if payload.get("errors"):
        message = payload["errors"][0].get("message", "unknown error")
        raise APIError(API_NAME, message)
    data = payload.get("data") or {}
    return data.get("objects") or []


async def get_country(client: httpx.AsyncClient, name: str) -> CountryResult:
    logger.info("Calling country API (country=%s)", name)
    if not settings.country_api_key:
        raise APIError(API_NAME, "COUNTRY_API_KEY is not configured")

    headers = {"Authorization": f"Bearer {settings.country_api_key}"}
    params = {"response_fields": FIELDS, "limit": 1}
    base = settings.country_url.rstrip("/")

    # Exact, case-insensitive match on the common name.
    objects = _objects(await fetch_json(
        client, f"{base}/names.common/{quote(name.strip())}",
        api_name=API_NAME, params=params, headers=headers,
    ))

    if not objects:
        logger.warning("No exact match for country %r; trying name search", name)
        objects = _objects(await fetch_json(
            client, f"{base}/name",
            api_name=API_NAME, params={**params, "q": name.strip()}, headers=headers,
        ))

    if not objects:
        raise APIError(API_NAME, f"country '{name}' not found")

    entry = objects[0]
    try:
        common_name = entry["names"]["common"]
        population = int(entry["population"])
    except (KeyError, TypeError, ValueError) as error:
        logger.error("Country API response is missing required fields")
        raise APIError(API_NAME, "invalid country response") from error

    capitals = entry.get("capitals") or []
    capital = None
    if capitals:
        primary = next(
            (c for c in capitals if (c.get("attributes") or {}).get("primary")),
            capitals[0],
        )
        capital = primary.get("name") if isinstance(primary, dict) else primary

    currencies = entry.get("currencies") or {}
    if isinstance(currencies, dict):
        currency = next(iter(currencies), None)
    elif isinstance(currencies, list) and currencies:
        first = currencies[0]
        currency = first.get("code") if isinstance(first, dict) else first
    else:
        currency = None

    if capital is None:
        logger.warning("Country API returned no capital for %s", common_name)
    if currency is None:
        logger.warning("Country API returned no currency for %s", common_name)

    return CountryResult(
        name=common_name,
        capital=capital,
        population=population,
        currency=currency,
    )