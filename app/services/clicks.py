"""Click recording and durable queue flushing."""

import json
import logging
from datetime import datetime

from app.cache.redis import RedisService
from app.database.repositories.clicks import insert_clicks
from app.models.click import ClickRecord

logger = logging.getLogger(__name__)
CLICK_BATCH_SIZE = 10


async def record_click(symbol: str, user_id: str | int | None, redis: RedisService) -> None:
    """Update ranking cache immediately and queue a click for batch persistence.

    Args:
        symbol: Stock ticker to record.
        user_id: Authenticated user identifier, or None for anonymous activity.
        redis: Application Redis service.
    """
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    try:
        if user_id is not None:
            user_key = str(user_id)
            current = await redis.get_user_weight(user_key, normalized_symbol) or 0.0
            await redis.set_user_weight(user_key, normalized_symbol, current + 1.0)
        payload = json.dumps({
            "symbol": normalized_symbol,
            "user_id": str(user_id) if user_id is not None else None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        await redis.push_click_to_queue(payload)
        if await redis.redis.llen(redis.KEY_CLICK_QUEUE) >= CLICK_BATCH_SIZE:
            await flush_click_queue(redis)
    except Exception:
        logger.error("Failed to record click for %s", normalized_symbol, exc_info=True)
        raise


async def flush_click_queue(redis: RedisService) -> int:
    """Drain the Redis click queue and insert its records in one transaction.

    Args:
        redis: Application Redis service whose queue should be drained.

    Returns:
        Number of records persisted. Invalid queue entries are logged and skipped.
    """
    records: list[ClickRecord] = []
    lock = redis.get_queue_lock()
    async with lock:
        while True:
            payload = await redis.pop_click_from_queue()
            if payload is None:
                break
            try:
                item = json.loads(payload)
                records.append(ClickRecord(
                    symbol=item["symbol"],
                    user_id=item.get("user_id"),
                    timestamp=datetime.strptime(item["timestamp"], "%Y-%m-%d %H:%M:%S"),
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Skipping malformed click queue item")
    return insert_clicks(records)
