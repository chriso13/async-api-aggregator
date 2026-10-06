from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AggregateRequest:
    city: str
    base_currency: str
    target_currency: str
    country: str | None = None
    units: str ="fahrenheit"


class _Serializable:
    def to_dict(self)-> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WeatherResult(_Serializable):
    city: str
    temperature: float
    condition: str
    units: str = "F"

@dataclass(frozen=True)
class ExchangeResult(_Serializable):
    base: str
    target: str
    rate: float
    date: str | None = None


@dataclass(frozen=True)
class CountryResult(_Serializable):
    name: str
    capital: str
    population: int
    currency: str | None