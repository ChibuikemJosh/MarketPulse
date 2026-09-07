"""yfinance adapter for historical candles and backend polling."""

import asyncio
import logging
from datetime import date, datetime

import yfinance as yf

from app.services.market_data.base import LiveMarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)


def _history(symbol: str, start: date, end: date, interval: str):
    """Run blocking yfinance history access in a worker thread."""
    return yf.Ticker(symbol).history(start=start, end=end, interval=interval, auto_adjust=False)


def _quote(symbol: str):
    """Run blocking yfinance quote access in a worker thread."""
    return yf.Ticker(symbol).history(period="1d", interval="1m", auto_adjust=False)


class YFinanceProvider(LiveMarketDataProvider):
    """Normalize yfinance responses without exposing pandas to callers."""

    name = "yfinance"

    async def historical_candles(self, instrument, start, end, interval):
        try:
            frame = await asyncio.to_thread(_history, instrument.provider_symbol(self.name), start, end, interval)
            candles: list[Candle] = []
            for timestamp, row in frame.dropna(subset=["Open", "High", "Low", "Close"]).iterrows():
                candles.append(Candle(
                    timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                    open=float(row["Open"]), high=float(row["High"]), low=float(row["Low"]), close=float(row["Close"]),
                    volume=float(row["Volume"]) if row.get("Volume") is not None else None,
                ))
            if not candles:
                return ProviderFailure(self.name, "historical_candles", "No candles returned", retryable=False)
            return candles
        except Exception as error:
            logger.warning("yfinance historical request failed for %s", instrument.symbol, exc_info=True)
            return ProviderFailure(self.name, "historical_candles", str(error), retryable=True)

    async def quote(self, instrument):
        return await self.live_quote(instrument)

    async def live_quote(self, instrument, as_of=None):
        try:
            frame = await asyncio.to_thread(_quote, instrument.provider_symbol(self.name))
            if frame.empty:
                return ProviderFailure(self.name, "quote", "No quote returned", retryable=False)
            row = frame.dropna(subset=["Close"]).iloc[-1]
            close = float(row["Close"])
            return Quote(symbol=instrument.symbol, price=close, volume=float(row["Volume"]), as_of=as_of or datetime.utcnow())
        except Exception as error:
            logger.warning("yfinance quote request failed for %s", instrument.symbol, exc_info=True)
            return ProviderFailure(self.name, "quote", str(error), retryable=True)
