"""TradingView screener adapter for configured market snapshots."""

import asyncio
import logging
from datetime import date

from tradingview_screener import Query

from app.services.market_data.base import MarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)


def _scan(market: str, ticker: str):
    """Run the blocking TradingView scanner query."""
    _, frame = (
        Query()
        .set_markets(market)
        .select("name", "open", "high", "low", "close", "volume", "change")
        .limit(5000)
        .get_scanner_data()
    )
    matches = frame[frame["name"] == ticker]
    return matches.iloc[-1] if not matches.empty else None


class TradingViewProvider(MarketDataProvider):
    """Use TradingView screener snapshots where market configuration supports it."""

    name = "tradingview"

    async def historical_candles(self, instrument: Instrument, start: date, end: date, interval: str):
        return ProviderFailure(self.name, "historical_candles", "Screener does not provide historical candle downloads", retryable=False)

    async def quote(self, instrument: Instrument):
        market = instrument.provider_symbols.get("tradingview_market") or _market_from_exchange(instrument.exchange)
        ticker = instrument.provider_symbol(self.name)
        if not market:
            return ProviderFailure(self.name, "quote", "No TradingView market mapping", retryable=False)
        try:
            row = await asyncio.to_thread(_scan, market, ticker)
            if row is None:
                return ProviderFailure(self.name, "quote", "Symbol was not returned by screener", retryable=False)
            close = _number(row.get("close"))
            return Quote(
                symbol=instrument.symbol,
                price=close,
                change_percent=_number(row.get("change")),
            )
        except Exception as error:
            logger.warning("TradingView screener request failed for %s", instrument.symbol, exc_info=True)
            return ProviderFailure(self.name, "quote", str(error), retryable=True)


def _number(value) -> float | None:
    """Convert pandas/numeric values while preserving missing data."""
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _market_from_exchange(exchange: str | None) -> str | None:
    """Map common exchange groups to TradingView screener markets."""
    return {"US": "america", "CA": "canada", "NG": "nigeria", "GB": "uk", "DE": "germany", "DK": "denmark"}.get(exchange or "")
