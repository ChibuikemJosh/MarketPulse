"""Personalized and global click-weight calculations."""

import logging
import math
from datetime import datetime, timedelta

from app.cache.redis import RedisService
from app.database.repositories.clicks import get_clicks_since

logger = logging.getLogger(__name__)
DECAY_RATE = 0.8
LOOKBACK_DAYS = 30


def _calculate_weights(rows: list[tuple[str, str]], now: datetime) -> dict[str, float]:
    """Apply exponential decay to database click rows."""
    weights: dict[str, float] = {}
    for symbol, timestamp in rows:
        try:
            clicked_at = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            days_old = max(0.0, (now - clicked_at).total_seconds() / 86400)
            weights[symbol] = weights.get(symbol, 0.0) + DECAY_RATE**days_old
        except (TypeError, ValueError):
            logger.warning("Ignoring malformed click timestamp for %s: %r", symbol, timestamp)
    return weights


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights logarithmically to the 0-100 ranking range."""
    total = sum(weights.values())
    if total <= 0:
        return {}
    denominator = math.log(total + 1)
    return {symbol: math.log(value + 1) / denominator * 100 for symbol, value in weights.items()}


async def load_user_weights(user_id: str | int | None, redis: RedisService) -> dict[str, float]:
    """Load one user's decayed click weights, using Redis as the read cache.

    Args:
        user_id: Authenticated user identifier, or None for an anonymous visitor.
        redis: Application Redis service.

    Returns:
        A symbol-to-weight mapping, or an empty mapping for anonymous users.
    """
    if user_id is None:
        return {}
    user_key = str(user_id)
    try:
        cached = await redis.get_user_weights(user_key)
        if cached:
            return cached
        since = datetime.now() - timedelta(days=LOOKBACK_DAYS)
        weights = _calculate_weights(get_clicks_since(since, user_key), datetime.now())
        normalized = _normalize(weights)
        for symbol, weight in normalized.items():
            await redis.set_user_weight(user_key, symbol, weight)
        return normalized
    except Exception:
        logger.error("Failed to load weights for user %s", user_id, exc_info=True)
        return {}


async def load_global_weights(redis: RedisService) -> dict[str, float]:
    """Aggregate recent clicks across users and cache normalized global weights.

    Args:
        redis: Application Redis service.

    Returns:
        A symbol-to-weight mapping normalized to the 0-100 range.
    """
    try:
        cached = await redis.get_global_weights()
        if cached:
            return cached
        now = datetime.now()
        since = now - timedelta(days=LOOKBACK_DAYS)
        weights = _normalize(_calculate_weights(get_clicks_since(since), now))
        await redis.set_global_weights(weights)
        return weights
    except Exception:
        logger.error("Failed to load global weights", exc_info=True)
        return {}
