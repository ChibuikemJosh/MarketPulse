"""Canonical market-data models shared by providers and API routes."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Instrument:
    """A canonical tradable identity with provider-specific symbols."""

    symbol: str
    exchange: str | None = None
    asset_type: str = "stock"
    currency: str | None = None
    timezone: str | None = None
    display_name: str | None = None
    provider_symbols: dict[str, str] = field(default_factory=dict)

    @property
    def instrument_id(self) -> str:
        """Return a stable identity that does not discard exchange information."""
        exchange = self.exchange or "global"
        return f"{self.asset_type}:{exchange}:{self.symbol}".upper()

    def provider_symbol(self, provider: str) -> str:
        """Return the provider symbol, falling back to the canonical symbol."""
        return self.provider_symbols.get(provider, self.symbol)


@dataclass(frozen=True)
class Candle:
    """One normalized OHLCV market-data candle."""

    timestamp: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None = None
    vwap: float | None = None


@dataclass(frozen=True)
class Quote:
    """A normalized latest quote or market snapshot."""

    symbol: str
    price: float | None
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: float | None = None
    as_of: datetime | None = None


@dataclass(frozen=True)
class ProviderFailure:
    """A provider failure that can be classified by the fallback orchestrator."""

    provider: str
    operation: str
    message: str
    retryable: bool = False
    status_code: int | None = None
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchMatch:
    """A provider or local search result tied to a canonical instrument."""

    instrument: Instrument
    score: float = 0.0
    source: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)
