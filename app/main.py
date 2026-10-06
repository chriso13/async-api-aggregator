"""Command-line entry point: parse arguments, run the aggregator, print JSON."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any

import httpx

from app.aggregator import aggregate, aggregate_sequential
from app.config import settings
from app.models.response import AggregateRequest

logger = logging.getLogger("app")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="async-api-aggregator",
        description="Fetch weather, exchange-rate and country data concurrently.",
    )
    parser.add_argument("--city", required=True, help="City for the weather lookup, e.g. Miami")
    parser.add_argument("--base", default="USD", help="Base currency code (default: USD)")
    parser.add_argument("--target", default="EUR", help="Target currency code (default: EUR)")
    parser.add_argument("--country", help="Country name, e.g. 'United States' (omit to skip)")
    parser.add_argument("--units", choices=["fahrenheit", "celsius"], default="fahrenheit")
    parser.add_argument(
        "--mode",
        choices=["concurrent", "sequential", "compare"],
        default="concurrent",
        help="'compare' runs both and reports the timings",
    )
    parser.add_argument("--log-level", default=settings.log_level, help="DEBUG, INFO, WARNING, ...")
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    # Logs go to stderr so stdout contains only the JSON result.
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # silence per-request noise


async def timed_run(request: AggregateRequest, concurrent: bool) -> tuple[dict[str, Any], float]:
    label = "Concurrent" if concurrent else "Sequential"
    # A fresh client per run so neither mode benefits from the other's warm connections.
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout),
        follow_redirects=True,
        headers={"User-Agent": "async-api-aggregator/1.0"},
    ) as client:
        start = time.perf_counter()
        runner = aggregate if concurrent else aggregate_sequential
        result = await runner(request, client)
        elapsed = time.perf_counter() - start
    logger.info("%s execution completed in %.2f seconds", label, elapsed)
    return result, elapsed


async def run(args: argparse.Namespace) -> dict[str, Any]:
    request = AggregateRequest(
        city=args.city,
        base_currency=args.base,
        target_currency=args.target,
        country=args.country,
        units=args.units,
    )

    if args.mode == "compare":
        _, sequential = await timed_run(request, concurrent=False)
        result, concurrent = await timed_run(request, concurrent=True)
        result["performance"] = {
            "sequential_seconds": round(sequential, 2),
            "concurrent_seconds": round(concurrent, 2),
            "speedup": round(sequential / concurrent, 2) if concurrent else None,
        }
    else:
        result, elapsed = await timed_run(request, concurrent=args.mode == "concurrent")
        result["performance"] = {"mode": args.mode, "elapsed_seconds": round(elapsed, 2)}
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    logger.info("Application started")
    try:
        result = asyncio.run(run(args))
        print(json.dumps(result, indent=2, ensure_ascii=False))

        sections = {k: v for k, v in result.items() if k != "performance"}
        all_failed = all("error" in section for section in sections.values())
        return 1 if all_failed else 0
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130
    finally:
        logger.info("Application finished")

if __name__ == "__main__":
    sys.exit(main())