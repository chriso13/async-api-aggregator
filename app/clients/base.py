"""Shared HTTP helper: GET JSON with retries, backoff and consistent errors."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 429 = rate limited; 5xx = transient server problems. Everything else fails fast.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 10.0


class APIError(Exception):
    """Raised when an upstream API call fails in a way callers should report."""

    def __init__(self, api_name: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{api_name}: {message}")
        self.api_name = api_name
        self.message = message
        self.status_code = status_code


def _error_detail(response: httpx.Response) -> str | None:
    """Pull a human-readable error message out of a JSON error body, if there is one."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    errors = body.get("errors")  # REST Countries v5 style
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return errors[0].get("message")
    for key in ("reason", "message", "error"):  # Open-Meteo uses "reason"
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    """Exponential backoff, honouring a numeric Retry-After header when present."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                pass  # HTTP-date form: fall back to backoff
    return settings.retry_backoff * 2 ** (attempt - 1)


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    api_name: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET `url` and return the decoded JSON body, retrying transient failures."""
    retries = settings.max_retries
    last_error = "unknown error"

    for attempt in range(1, retries + 1):
        retry_response: httpx.Response | None = None
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            logger.debug("%s API response body: %s", api_name, response.text[:500])
            data = response.json()

            # Some APIs return HTTP 200 with an error payload; don't treat that as success.
            if isinstance(data, dict) and data.get("success") is False:
                detail = _error_detail(response) or "API reported failure"
                logger.error("%s API returned an error payload: %s", api_name, detail)
                raise APIError(api_name, detail, status_code=response.status_code)

            logger.info(
                "%s API request completed (HTTP %d, attempt %d/%d)",
                api_name, response.status_code, attempt, retries,
            )
            return data

        except httpx.TimeoutException:
            last_error = "request timed out"
            logger.warning("%s API attempt %d/%d timed out", api_name, attempt, retries)

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            detail = _error_detail(error.response)
            message = f"HTTP {status}" + (f" ({detail})" if detail else "")
            if status not in RETRYABLE_STATUS_CODES:
                logger.error("%s API request failed: %s", api_name, message)
                raise APIError(api_name, message, status_code=status) from error
            last_error = message
            retry_response = error.response
            logger.warning("%s API attempt %d/%d failed: %s", api_name, attempt, retries, message)

        except httpx.RequestError as error:
            last_error = f"connection error ({error.__class__.__name__})"
            logger.warning("%s API attempt %d/%d failed: %s", api_name, attempt, retries, last_error)

        except ValueError as error:  # JSONDecodeError is a ValueError subclass
            logger.error("%s API request failed: response was not valid JSON", api_name)
            raise APIError(api_name, "invalid JSON response") from error

        if attempt < retries:
            delay = _retry_delay(attempt, retry_response)
            logger.debug("%s API retrying in %.2f seconds", api_name, delay)
            await asyncio.sleep(delay)

    logger.error("%s API request failed after %d attempts: %s", api_name, retries, last_error)
    raise APIError(api_name, f"unavailable after {retries} attempts ({last_error})")