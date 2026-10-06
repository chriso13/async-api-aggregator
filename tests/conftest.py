"""Shared pytest fixtures."""
from __future__ import annotations

from typing import Callable

import httpx
import pytest

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
async def make_client():
    """Factory that builds an httpx.AsyncClient backed by a fake transport.

    Usage in a test:
        client = make_client(lambda request: httpx.Response(200, json={...}))

    No real network calls are made: every request goes to `handler`.
    Clients are closed automatically after the test.
    """
    clients: list[httpx.AsyncClient] = []

    def _make(handler: Handler) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    yield _make

    for client in clients:
        await client.aclose()