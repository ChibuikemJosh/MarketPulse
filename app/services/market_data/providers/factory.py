"""Construction of the configured market-data provider chain."""

from app.core import config
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.providers.massive import MassiveProvider
from app.services.market_data.providers.tiingo import TiingoProvider
from app.services.market_data.providers.tradingview import TradingViewProvider
from app.services.market_data.providers.yfinance import YFinanceProvider


def build_default_providers() -> list[MarketDataProvider]:
    """Build providers in the requested historical/live fallback order."""
    candidates: dict[str, MarketDataProvider] = {
        "tradingview": TradingViewProvider(),
        "yfinance": YFinanceProvider(),
        "massive": MassiveProvider(),
        "tiingo": TiingoProvider(),
    }
    return [provider for name, provider in candidates.items() if config.PROVIDER_ENABLED.get(name, False)]