"""Historical candle service built on the provider orchestrator."""

from datetime import date

from app.services.market_data.models import Candle, Instrument, ProviderFailure
from app.services.market_data.orchestrator import MarketDataOrchestrator


class HistoricalMarketDataService:
    """Application service for daily and long-range candle requests."""

    def __init__(self, orchestrator: MarketDataOrchestrator):
        self.orchestrator = orchestrator

    async def get_candles(self, instrument: Instrument, start: date, end: date, interval: str = "1d") -> list[Candle] | ProviderFailure:
        """Return normalized candles using the configured historical fallback chain."""
        return await self.orchestrator.historical_candles(instrument, start, end, interval)
