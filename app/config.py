"""Application settings loaded from environment variables (and .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return raw.strip() if raw and raw.strip() else default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from error


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from error


@dataclass(frozen=True)
class Settings:
    request_timeout: float
    max_retries: int
    retry_backoff: float
    log_level: str
    geocoding_url: str
    forecast_url: str
    exchange_url: str
    country_url: str
    country_api_key: str

    def __repr__(self) -> str:
        # Never print the API key in logs or tracebacks.
        masked = "***" if self.country_api_key else "<not set>"
        return (
            f"Settings(request_timeout={self.request_timeout}, max_retries={self.max_retries}, "
            f"retry_backoff={self.retry_backoff}, log_level={self.log_level!r}, "
            f"country_url={self.country_url!r}, country_api_key={masked})"
        )


def load_settings() -> Settings:
    return Settings(
        request_timeout=_get_float("REQUEST_TIMEOUT", 5.0),
        max_retries=max(1, _get_int("MAX_RETRIES", 3)),
        retry_backoff=_get_float("RETRY_BACKOFF", 0.5),
        log_level=_get_str("LOG_LEVEL", "INFO"),
        geocoding_url=_get_str("GEOCODING_API_URL", "https://geocoding-api.open-meteo.com/v1/search"),
        forecast_url=_get_str("WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"),
        exchange_url=_get_str("EXCHANGE_API_URL", "https://api.frankfurter.dev/v1/latest"),
        country_url=_get_str("COUNTRY_API_URL", "https://api.restcountries.com/countries/v5"),
        country_api_key=_get_str("COUNTRY_API_KEY", ""),
    )


settings = load_settings()