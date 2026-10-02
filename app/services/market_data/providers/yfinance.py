"""yfinance adapter for historical candles and backend polling."""

import asyncio
import logging
from datetime import date, datetime

import yfinance as yf

from app.services.market_data.base import LiveMarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)
# yfinance logs expected missing-symbol messages at error level. Provider
# failures are normalized and reported by this adapter instead.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def _history(symbol: str, start: date, end: date, interval: str):
    """Run blocking yfinance history access in a worker thread."""
    return yf.Ticker(symbol).history(start=start, end=end, interval=interval, auto_adjust=False)


def _quote(symbol: str):
    """Run blocking yfinance quote access in a worker thread."""
    return yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)


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
            logger.debug("yfinance historical request failed for %s: %s", instrument.symbol, error)
            return ProviderFailure(
                self.name,
                "historical_candles",
                "provider_data_unavailable",
                retryable=False,
                details={"reason": "historical_data_unavailable"},
            )

    async def quote(self, instrument):
        return await self.live_quote(instrument)

    async def live_quote(self, instrument, as_of=None):
        try:
            frame = await asyncio.to_thread(_quote, instrument.provider_symbol(self.name))
            if frame.empty:
                return ProviderFailure(self.name, "quote", "No quote returned", retryable=False)
            rows = frame.dropna(subset=["Close"])
            if rows.empty:
                return ProviderFailure(self.name, "quote", "No quote returned", retryable=False)
            row = rows.iloc[-1]
            close = float(row["Close"])
            previous_close = float(rows.iloc[-2]["Close"]) if len(rows) > 1 else None
            change = close - previous_close if previous_close is not None else None
            change_percent = (change / previous_close * 100) if previous_close else None
            timestamp = rows.index[-1]
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            return Quote(
                symbol=instrument.symbol,
                price=close,
                previous_close=previous_close,
                change=change,
                change_percent=change_percent,
                volume=float(row["Volume"]) if row.get("Volume") is not None else None,
                as_of=as_of or timestamp,
            )
        except Exception as error:
            logger.debug("yfinance quote request failed for %s: %s", instrument.symbol, error)
            return ProviderFailure(
                self.name,
                "quote",
                "provider_data_unavailable",
                retryable=False,
                details={"reason": "quote_data_unavailable"},
            )
