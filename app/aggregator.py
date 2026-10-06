"""Run the API clients and combine their results into one response."""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Awaitable, Callable, Iterable

import httpx

from app.clients.base import APIError
from app.clients.country import get_country
from app.clients.exchange import get_exchange_rate
from app.clients.weather import get_weather
from app.models.response import AggregateRequest

logger = logging.getLogger(__name__)

TaskFactory = Callable[[], Awaitable[Any]]


def _build_tasks(request: AggregateRequest, client: httpx.AsyncClient) -> dict[str, TaskFactory]:
    tasks: dict[str, TaskFactory] = {
        "weather": partial(get_weather, client, request.city, request.units),
        "exchange": partial(
            get_exchange_rate, client, request.base_currency, request.target_currency
        ),
    }
    if request.country:
        tasks["country"] = partial(get_country, client, request.country)
    return tasks


def _to_section(name: str, outcome: Any) -> dict[str, Any]:
    if isinstance(outcome, APIError):
        return {"error": f"{name.capitalize()} API unavailable: {outcome.message}"}
    if isinstance(outcome, Exception):
        logger.error("Unexpected error in %s client", name, exc_info=outcome)
        return {"error": f"{name.capitalize()} API failed unexpectedly"}
    if isinstance(outcome, BaseException):  # e.g. CancelledError: don't swallow it
        raise outcome
    return outcome.to_dict()


def _combine(names: Iterable[str], outcomes: Iterable[Any]) -> dict[str, Any]:
    result = {name: _to_section(name, outcome) for name, outcome in zip(names, outcomes)}
    failed = [name for name, section in result.items() if "error" in section]
    if failed:
        logger.warning("Aggregation completed with %d failed API(s): %s", len(failed), ", ".join(failed))
    else:
        logger.info("Aggregation completed: all %d APIs succeeded", len(result))
    return result


async def aggregate(request: AggregateRequest, client: httpx.AsyncClient) -> dict[str, Any]:
    """Call all APIs concurrently. One failure does not cancel the others."""
    tasks = _build_tasks(request, client)
    outcomes = await asyncio.gather(
        *(factory() for factory in tasks.values()),
        return_exceptions=True,
    )
    return _combine(tasks.keys(), outcomes)


async def aggregate_sequential(request: AggregateRequest, client: httpx.AsyncClient) -> dict[str, Any]:
    """Call the APIs one after another. Exists only for the performance comparison."""
    tasks = _build_tasks(request, client)
    outcomes: list[Any] = []
    for factory in tasks.values():
        try:
            outcomes.append(await factory())
        except Exception as error:
            outcomes.append(error)
    return _combine(tasks.keys(), outcomes)
