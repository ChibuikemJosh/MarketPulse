"""Tiingo REST adapter for end-of-day historical candles."""

from datetime import date, datetime, timezone
import logging

import httpx

from app.core import config
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)


class TiingoProvider(MarketDataProvider):
    """Fetch Tiingo daily candles when a token is configured."""

    name = "tiingo"
    base_url = "https://api.tiingo.com"

    def __init__(self, api_key: str = config.TIINGO_API_KEY):
        self.api_key = api_key

    async def historical_candles(self, instrument, start: date, end: date, interval: str):
        if not self.api_key:
            return ProviderFailure(self.name, "historical_candles", "Provider is disabled", retryable=False)
        if interval not in {"1d", "1wk", "1mo"}:
            return ProviderFailure(self.name, "historical_candles", "Tiingo adapter supports daily intervals only", retryable=False)
        url = f"{self.base_url}/tiingo/daily/{instrument.provider_symbol(self.name)}/prices"
        try:
            async with httpx.AsyncClient(timeout=config.PROVIDER_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params={"startDate": start.isoformat(), "endDate": end.isoformat(), "token": self.api_key})
            if response.status_code in {429, 500, 502, 503, 504}:
                return ProviderFailure(self.name, "historical_candles", response.text, retryable=True, status_code=response.status_code)
            response.raise_for_status()
            candles = [Candle(
                timestamp=datetime.fromisoformat(item["date"].replace("Z", "+00:00")).astimezone(timezone.utc),
                open=item.get("adjOpen", item.get("open")), high=item.get("adjHigh", item.get("high")),
                low=item.get("adjLow", item.get("low")), close=item.get("adjClose", item.get("close")), volume=item.get("volume"),
            ) for item in response.json()]
            return candles or ProviderFailure(self.name, "historical_candles", "No candles returned", retryable=False)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            logger.warning("Tiingo historical request failed for %s", instrument.symbol, exc_info=True)
            return ProviderFailure(self.name, "historical_candles", str(error), retryable=True)

    async def quote(self, instrument):
        return ProviderFailure(self.name, "quote", "Quote endpoint not implemented", retryable=False)
