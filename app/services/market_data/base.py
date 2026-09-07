"""Interfaces for capability-specific market-data providers."""

from abc import ABC, abstractmethod
from datetime import date, datetime

from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote, SearchMatch


class MarketDataProvider(ABC):
    """Base contract for optional market-data provider adapters."""

    name: str

    @abstractmethod
    async def historical_candles(
        self,
        instrument: Instrument,
        start: date,
        end: date,
        interval: str,
    ) -> list[Candle] | ProviderFailure:
        """Return normalized historical candles or a structured failure."""

    @abstractmethod
    async def quote(self, instrument: Instrument) -> Quote | ProviderFailure:
        """Return a normalized quote or a structured failure."""

    async def search(self, query: str) -> list[SearchMatch] | ProviderFailure:
        """Search provider symbols when the provider supports discovery."""
        return ProviderFailure(self.name, "search", "Search is not supported", retryable=False)


class LiveMarketDataProvider(MarketDataProvider):
    """Optional extension for providers that can stream or poll live data."""

    @abstractmethod
    async def live_quote(self, instrument: Instrument, as_of: datetime | None = None) -> Quote | ProviderFailure:
        """Return the latest available live quote."""
