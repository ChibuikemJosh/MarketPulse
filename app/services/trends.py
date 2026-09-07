"""Periodic market trend and display-name cache refresh."""

import asyncio
import logging

import yfinance as yf

from app.cache.redis import RedisService
from app.config.loader import load_brand_map, load_market_map
from app.services.search import clean_stock_name

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 600


def calculate_price_change(symbol: str) -> float:
    """Calculate the latest two-session percentage move with yfinance.

    Args:
        symbol: Stock ticker accepted by yfinance.

    Returns:
        Percentage change, or 0.0 when market data is unavailable.
    """
    try:
        history = yf.Ticker(symbol).history(period="2d")
        if len(history) < 2:
            return 0.0
        previous = float(history["Close"].iloc[-2])
        latest = float(history["Close"].iloc[-1])
        return ((latest - previous) / previous) * 100 if previous else 0.0
    except Exception:
        logger.error("Failed to calculate price change for %s", symbol, exc_info=True)
        return 0.0


async def refresh_market_cache_once(redis: RedisService) -> None:
    """Refresh trends and fallback display names for configured symbols.

    TradingView integration can be added behind this boundary; the current
    fallback deliberately uses yfinance and keeps failures per-symbol.
    """
    brand_map = load_brand_map()
    market_map = load_market_map()
    del market_map  # The map is loaded here so this service owns market refresh inputs.
    for symbol, aliases in brand_map.items():
        try:
            change = await asyncio.to_thread(calculate_price_change, symbol)
            await redis.update_trending_score(symbol, round(change, 2))
            if not await redis.get_cached_name(symbol):
                raw_name = aliases[0] if isinstance(aliases, list) and aliases else symbol.split(".")[0]
                await redis.set_cached_name(symbol, clean_stock_name(str(raw_name)))
        except Exception:
            logger.error("Failed to refresh cache for %s", symbol, exc_info=True)


async def refresh_market_cache(redis: RedisService) -> None:
    """Run cache refresh every ten minutes until the application shuts down."""
    while True:
        try:
            await refresh_market_cache_once(redis)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Market cache refresh failed", exc_info=True)
        await asyncio.sleep(REFRESH_SECONDS)
