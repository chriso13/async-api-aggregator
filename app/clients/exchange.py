from __future__ import annotations
import logging
import httpx

from app.clients.base import APIError, fetch_json
from app.config import settings
from app.models.response import ExchangeResult

logger = logging.getLogger(__name__)

API_NAME = "exchange"


async def get_exchange_rate(
        client: httpx.AsyncClient, base: str, target: str
) -> ExchangeResult:
    base, target = base.strip().upper(), target.strip().upper()
    logger.info("Calling exchange API (%s -> %s)", base, target)

    if base == target:
        logger.info("Base and target currency are the same;  skipping exchange API call")
        return ExchangeResult(base=base, target=target,rate=1.0)

    data = await fetch_json(
        client,
        settings.exchange_url,
        api_name=API_NAME,
        params={"from": base, "to": target}
    )

    if not isinstance(data,dict):
        raise APIError(API_NAME, "unexpected response format")

    try:
        rate = data["rates"][target]
    except (KeyError, TypeError) as error:
        logger.error("Excahnge API response has no rate for  %s", target)
        raise APIError(API_NAME, f"rate for {target} missing from response") from error

    if isinstance(rate, bool) or not isinstance(rate, (int,  float)) or rate <= 0:
        logger.error("Exchange API returned an invalid rate: %r", rate)
        raise APIError(API_NAME, f"invalid rate lavue: {rate!r}")

    return ExchangeResult(
        base=data.get("base",base),
        target=target,
        rate=float(rate),
        date=data.get("date")
    )