"""Reliable fallback orchestration for normalized market-data capabilities."""

import asyncio
from dataclasses import asdict
import logging
import time
from collections.abc import Sequence
from datetime import date, datetime, timezone

from app.cache.redis import RedisService
from app.core import config
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote

logger = logging.getLogger(__name__)


def _cached_candle(item: dict) -> Candle:
    """Restore a cached candle timestamp to the model's datetime type."""
    timestamp = item["timestamp"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return Candle(
        timestamp=timestamp,
        open=item.get("open"),
        high=item.get("high"),
        low=item.get("low"),
        close=item.get("close"),
        volume=item.get("volume"),
        vwap=item.get("vwap"),
    )


def _cached_quote(item: dict) -> Quote:
    """Restore a cached quote timestamp to the model's datetime type."""
    as_of = item.get("as_of")
    if isinstance(as_of, str):
        as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    return Quote(
        symbol=item["symbol"],
        price=item.get("price"),
        previous_close=item.get("previous_close"),
        change=item.get("change"),
        change_percent=item.get("change_percent"),
        volume=item.get("volume"),
        as_of=as_of,
    )


class MarketDataOrchestrator:
    """Try providers in order with timeout, cache, retry, and circuit state."""

    def __init__(self, providers: Sequence[MarketDataProvider], redis: RedisService | None = None):
        self.providers = list(providers)
        self.redis = redis
        self._open_until: dict[str, float] = {}

    def _available(self, provider: MarketDataProvider) -> bool:
        return time.monotonic() >= self._open_until.get(provider.name, 0.0)

    def _record_failure(self, provider: MarketDataProvider, failure: ProviderFailure) -> None:
        if failure.retryable:
            self._open_until[provider.name] = time.monotonic() + config.PROVIDER_CIRCUIT_BREAKER_SECONDS

    async def historical_candles(self, instrument: Instrument, start: date, end: date, interval: str) -> list[Candle] | ProviderFailure:
        """Fetch candles using the configured provider fallback order."""
        failures: list[ProviderFailure] = []
        for provider in self.providers:
            if not self._available(provider) or await self._is_open(provider, "historical_candles"):
                continue
            cache_key = self._cache_key("candles", instrument, provider.name, interval, start.isoformat(), end.isoformat())
            cached = await self._read_cache(cache_key)
            if cached is not None:
                try:
                    return [_cached_candle(item) for item in cached.get("data", [])]
                except (TypeError, ValueError):
                    logger.warning("Ignoring malformed candle cache for %s", instrument.instrument_id)
            failure = await self._read_failure("historical_candles", instrument.instrument_id, provider.name, interval, start.isoformat(), end.isoformat())
            if failure is not None:
                failures.append(ProviderFailure(provider.name, "historical_candles", failure.get("error", "cached provider failure"), retryable=False))
                continue
            result = await self._call_with_retry(provider.name, provider.historical_candles, instrument, start, end, interval)
            if isinstance(result, list) and result:
                await self._write_cache(cache_key, provider.name, result, config.HISTORICAL_CACHE_TTL_SECONDS)
                return result
            if isinstance(result, ProviderFailure):
                failures.append(result)
                await self._handle_failure(provider, result, "historical_candles", instrument.instrument_id, interval, start.isoformat(), end.isoformat())
        return _combined_failure("historical_candles", failures)

    async def quote(self, instrument: Instrument) -> Quote | ProviderFailure:
        """Fetch a quote using the configured provider fallback order."""
        failures: list[ProviderFailure] = []
        for provider in self.providers:
            if not self._available(provider) or await self._is_open(provider, "quote"):
                continue
            cache_key = self._cache_key("quote", instrument, provider.name)
            cached = await self._read_cache(cache_key)
            if cached is not None:
                try:
                    return _cached_quote(cached["data"])
                except (KeyError, TypeError, ValueError):
                    logger.warning("Ignoring malformed quote cache for %s", instrument.instrument_id)
            failure = await self._read_failure("quote", instrument.instrument_id, provider.name)
            if failure is not None:
                failures.append(ProviderFailure(provider.name, "quote", failure.get("error", "cached provider failure"), retryable=False))
                continue
            result = await self._call_with_retry(provider.name, provider.quote, instrument)
            if isinstance(result, Quote):
                await self._write_cache(cache_key, provider.name, result, config.PROVIDER_CACHE_TTL_SECONDS)
                return result
            if isinstance(result, ProviderFailure):
                failures.append(result)
                await self._handle_failure(provider, result, "quote", instrument.instrument_id)
        return _combined_failure("quote", failures)

    async def _call_with_retry(self, provider_name: str, operation, *args):
        """Apply timeout and limited retry policy to one provider operation."""
        attempts = config.PROVIDER_RETRY_COUNT + 1
        last_failure: ProviderFailure | None = None
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(operation(*args), timeout=config.PROVIDER_TIMEOUT_SECONDS)
                if isinstance(result, ProviderFailure) and result.retryable:
                    last_failure = result
                else:
                    return result
            except asyncio.TimeoutError:
                last_failure = ProviderFailure(provider_name, operation.__name__, "Provider request timed out", retryable=True)
            except Exception as error:
                last_failure = ProviderFailure(provider_name, operation.__name__, str(error), retryable=True)
            if attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (attempt + 1))
        return last_failure or ProviderFailure(provider_name, operation.__name__, "Provider request failed", retryable=True)

    async def _handle_failure(self, provider: MarketDataProvider, failure: ProviderFailure, operation: str, instrument_id: str, interval: str = "", start: str = "", end: str = "") -> None:
        """Record local and shared circuit state for retryable failures."""
        self._record_failure(provider, failure)
        if self.redis and failure.retryable:
            try:
                await self.redis.mark_provider_failure(provider.name, operation)
                await self.redis.set_market_failure(operation, instrument_id, provider.name, {"provider": provider.name, "operation": operation, "error": failure.message, "is_stale": True}, 60, interval, start, end)
            except Exception:
                logger.warning("Could not update provider circuit state", exc_info=True)

    def _cache_key(self, operation: str, instrument: Instrument, provider: str, interval: str = "", start: str = "", end: str = "") -> str:
        """Build a provider- and range-specific cache key."""
        if self.redis is None:
            return ""
        return self.redis.market_cache_key(operation, instrument.instrument_id, provider, interval, start, end)

    async def _read_cache(self, key: str) -> dict | None:
        """Read a cache record, tolerating Redis outages."""
        if not self.redis or not key:
            return None
        try:
            return await self.redis.get_market_cache(key)
        except Exception:
            logger.warning("Market cache read failed", exc_info=True)
            return None

    async def _read_failure(self, operation: str, instrument_id: str, provider: str, interval: str = "", start: str = "", end: str = "") -> dict | None:
        """Read a short-lived exact-request failure before calling a provider."""
        if not self.redis:
            return None
        try:
            return await self.redis.get_market_failure(operation, instrument_id, provider, interval, start, end)
        except Exception:
            logger.warning("Market failure cache read failed", exc_info=True)
            return None

    async def _write_cache(self, key: str, provider: str, data: list[Candle] | Quote, ttl: int) -> None:
        """Write normalized data with provider and freshness metadata."""
        if not self.redis or not key:
            return
        record = {
            "provider": provider,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "is_stale": False,
            "data": [asdict(item) for item in data] if isinstance(data, list) else asdict(data),
        }
        try:
            await self.redis.set_market_cache(key, record, ttl)
        except Exception:
            logger.warning("Market cache write failed", exc_info=True)

    async def _is_open(self, provider: MarketDataProvider, operation: str) -> bool:
        """Check shared provider circuit state when Redis is configured."""
        if self.redis is None:
            return False
        try:
            return await self.redis.provider_is_open(provider.name, operation)
        except Exception:
            return False


def _combined_failure(operation: str, failures: list[ProviderFailure]) -> ProviderFailure:
    """Return structured failure details without inventing a market value."""
    return ProviderFailure(
        provider="orchestrator",
        operation=operation,
        message="All market-data providers failed",
        retryable=any(failure.retryable for failure in failures),
        occurred_at=datetime.now(timezone.utc),
        details={"failures": [asdict(failure) for failure in failures]},
    )
