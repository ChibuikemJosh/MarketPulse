"""Backend live quote service; browser charts remain TradingView widgets."""

from app.services.market_data.models import Instrument, ProviderFailure, Quote
from app.services.market_data.orchestrator import MarketDataOrchestrator


class LiveMarketDataService:
    """Application service for backend quote polling and analysis."""

    def __init__(self, orchestrator: MarketDataOrchestrator):
        self.orchestrator = orchestrator

    async def get_quote(self, instrument: Instrument) -> Quote | ProviderFailure:
        """Return the freshest quote available from the provider chain."""
        return await self.orchestrator.quote(instrument)
