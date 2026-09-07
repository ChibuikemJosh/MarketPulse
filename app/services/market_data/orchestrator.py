"""Fallback orchestration for normalized market-data capabilities."""

import asyncio
import logging
import time
from collections.abc import Sequence
from datetime import date, datetime, timezone

from app.core import config
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)


class MarketDataOrchestrator:
    """Try providers in order and return the first successful normalized result.

    The circuit breaker is process-local for now. It prevents a failing provider
    from delaying every request and can later be moved to Redis for multi-worker
    deployments without changing the provider interface.
    """

    def __init__(self, providers: Sequence[MarketDataProvider]):
        self.providers = list(providers)
        self._open_until: dict[str, float] = {}
        self._last_failures: dict[str, ProviderFailure] = {}

    def _available(self, provider: MarketDataProvider) -> bool:
        return time.monotonic() >= self._open_until.get(provider.name, 0.0)

    def _record_failure(self, provider: MarketDataProvider, failure: ProviderFailure) -> None:
        self._last_failures[provider.name] = failure
        if failure.retryable:
            self._open_until[provider.name] = time.monotonic() + 30.0

    async def historical_candles(self, instrument: Instrument, start: date, end: date, interval: str) -> list[Candle] | ProviderFailure:
        """Fetch candles using configured provider fallback order."""
        failures: list[ProviderFailure] = []
        for provider in self.providers:
            if not self._available(provider):
                continue
            result = await self._call_with_retry(provider.historical_candles, instrument, start, end, interval)
            if isinstance(result, list) and result:
                return result
            if isinstance(result, ProviderFailure):
                failures.append(result)
                self._record_failure(provider, result)
        return _combined_failure("historical_candles", failures)

    async def quote(self, instrument: Instrument) -> Quote | ProviderFailure:
        """Fetch a quote using configured provider fallback order."""
        failures: list[ProviderFailure] = []
        for provider in self.providers:
            if not self._available(provider):
                continue
            result = await self._call_with_retry(provider.quote, instrument)
            if isinstance(result, Quote):
                return result
            if isinstance(result, ProviderFailure):
                failures.append(result)
                self._record_failure(provider, result)
        return _combined_failure("quote", failures)

    async def _call_with_retry(self, operation, *args):
        """Apply timeout and limited retry policy to one provider operation."""
        attempts = config.PROVIDER_RETRY_COUNT + 1
        last_failure: ProviderFailure | None = None
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(operation(*args), timeout=config.PROVIDER_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                last_failure = ProviderFailure("unknown", operation.__name__, "Provider request timed out", retryable=True)
            except Exception as error:
                last_failure = ProviderFailure("unknown", operation.__name__, str(error), retryable=True)
            if attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (attempt + 1))
        return last_failure or ProviderFailure("unknown", operation.__name__, "Provider request failed", retryable=True)


def _combined_failure(operation: str, failures: list[ProviderFailure]) -> ProviderFailure:
    """Return structured failure details without inventing a market value."""
    return ProviderFailure(
        provider="orchestrator",
        operation=operation,
        message="All market-data providers failed",
        retryable=any(failure.retryable for failure in failures),
        occurred_at=datetime.now(timezone.utc),
        details={"failures": [failure.__dict__ for failure in failures]},
    )
