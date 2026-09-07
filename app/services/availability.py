"""External API quota and availability checks."""

import logging

from app.cache.redis import RedisService
from app.core.config import API_LIMITS

logger = logging.getLogger(__name__)


async def can_call_alpha_vantage_api(redis: RedisService) -> bool:
    """Return whether today's Alpha Vantage request quota remains.

    Args:
        redis: Application Redis service storing the daily atomic counter.

    Returns:
        True when another request is permitted, otherwise False.
    """
    try:
        calls = await redis.get_alpha_vantage_calls()
        return calls < API_LIMITS["ALPHA_VANTAGE"]
    except Exception:
        logger.error("Unable to read Alpha Vantage quota", exc_info=True)
        return False
