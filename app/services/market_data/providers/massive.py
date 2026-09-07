"""Massive (formerly Polygon) REST adapter."""

from datetime import date, datetime, timezone
import logging

import httpx

from app.core import config
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)


class MassiveProvider(MarketDataProvider):
    """Fetch stock aggregates from Massive when an API key is configured."""

    name = "massive"
    base_url = "https://api.massive.com"

    def __init__(self, api_key: str = config.MASSIVE_API_KEY):
        self.api_key = api_key

    async def historical_candles(self, instrument, start: date, end: date, interval: str):
        if not self.api_key:
            return ProviderFailure(self.name, "historical_candles", "Provider is disabled", retryable=False)
        multiplier, timespan = _interval(interval)
        url = f"{self.base_url}/v2/aggs/ticker/{instrument.provider_symbol(self.name)}/range/{multiplier}/{timespan}/{start}/{end}"
        try:
            async with httpx.AsyncClient(timeout=config.PROVIDER_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key})
            if response.status_code in {429, 500, 502, 503, 504}:
                return ProviderFailure(self.name, "historical_candles", response.text, retryable=True, status_code=response.status_code)
            response.raise_for_status()
            payload = response.json()
            candles = [Candle(
                timestamp=datetime.fromtimestamp(item["t"] / 1000, tz=timezone.utc),
                open=item.get("o"), high=item.get("h"), low=item.get("l"), close=item.get("c"),
                volume=item.get("v"), vwap=item.get("vw"),
            ) for item in payload.get("results", [])]
            return candles or ProviderFailure(self.name, "historical_candles", "No candles returned", retryable=False)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            logger.warning("Massive historical request failed for %s", instrument.symbol, exc_info=True)
            return ProviderFailure(self.name, "historical_candles", str(error), retryable=True)

    async def quote(self, instrument):
        return ProviderFailure(self.name, "quote", "Quote endpoint not implemented", retryable=False)


def _interval(interval: str) -> tuple[int, str]:
    """Convert application intervals to Massive aggregate path components."""
    mapping = {"1m": (1, "minute"), "5m": (5, "minute"), "15m": (15, "minute"), "1h": (1, "hour"), "1d": (1, "day"), "1wk": (1, "week"), "1mo": (1, "month")}
    return mapping.get(interval, (1, "day"))
