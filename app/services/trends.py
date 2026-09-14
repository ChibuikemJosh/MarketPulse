"""Bounded, provider-backed trend refresh for configured instruments."""

import asyncio
from datetime import datetime, timezone
import logging

from app.cache.redis import RedisService
from app.config.loader import load_brand_map
from app.core import config
from app.services.market_data.models import Instrument, ProviderFailure
from app.services.market_data.normalization import load_instrument_registry
from app.services.market_data.orchestrator import MarketDataOrchestrator
from app.services.market_data.providers.factory import build_default_providers
from app.services.search import clean_stock_name

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 600


def _change_percent(price: float | None, previous_close: float | None, direct_change: float | None) -> float | None:
    """Calculate a trend percentage without manufacturing a zero on failure."""
    if direct_change is not None:
        return direct_change
    if price is None or previous_close in (None, 0):
        return None
    return ((price - previous_close) / previous_close) * 100


async def _refresh_one(
    instrument: Instrument,
    aliases: list[str],
    orchestrator: MarketDataOrchestrator,
    redis: RedisService,
    semaphore: asyncio.Semaphore,
) -> None:
    """Refresh one instrument while limiting provider concurrency."""
    async with semaphore:
        try:
            quote = await orchestrator.quote(instrument)
            if isinstance(quote, ProviderFailure):
                await redis.update_trending_metadata(instrument.symbol, {
                    "status": "error",
                    "is_stale": True,
                    "provider": quote.provider,
                    "error": quote.message,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                return

            change = _change_percent(quote.price, quote.previous_close, quote.change_percent)
            if change is not None:
                await redis.update_trending_score(instrument.symbol, round(change, 2))
            await redis.update_trending_metadata(instrument.symbol, {
                "status": "ok",
                "is_stale": False,
                "provider": "orchestrator",
                "as_of": quote.as_of.isoformat() if quote.as_of else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            if not await redis.get_cached_name(instrument.symbol):
                fallback_name = clean_stock_name(str(aliases[0])) if aliases else instrument.symbol
                await redis.set_cached_name(instrument.symbol, fallback_name)
        except Exception:
            logger.error("Failed to refresh trend for %s", instrument.symbol, exc_info=True)
            await redis.update_trending_metadata(instrument.symbol, {
                "status": "error",
                "is_stale": True,
                "provider": "orchestrator",
                "error": "Unexpected refresh failure",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })


async def refresh_market_cache_once(redis: RedisService) -> None:
    """Refresh trend snapshots using market-configured canonical instruments."""
    registry = load_instrument_registry()
    brand_map = load_brand_map()
    orchestrator = MarketDataOrchestrator(build_default_providers(), redis=redis)
    semaphore = asyncio.Semaphore(config.MARKET_REFRESH_CONCURRENCY)
    await asyncio.gather(*(
        _refresh_one(
            instrument,
            brand_map.get(symbol, []) if isinstance(brand_map.get(symbol, []), list) else [],
            orchestrator,
            redis,
            semaphore,
        )
        for symbol, instrument in registry.items()
    ))


async def refresh_market_cache(redis: RedisService) -> None:
    """Run one refresh leader every ten minutes without duplicate workers."""
    while True:
        try:
            lock = redis.get_refresh_lock()
            acquired = await lock.acquire(blocking=False)
            if acquired:
                try:
                    await refresh_market_cache_once(redis)
                finally:
                    await lock.release()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Market cache refresh failed", exc_info=True)
        await asyncio.sleep(REFRESH_SECONDS)
