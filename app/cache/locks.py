from redis.asyncio import Redis as RedisClient
from redis.asyncio.lock import Lock

from app.core.config import REDIS_QUEUE_LOCK_TIMEOUT, REDIS_CACHE_LOCK_TIMEOUT
from app.cache.keys import CLICK_QUEUE_LOCK, GLOBAL_CACHE_LOCK

def get_queue_lock(
    redis: RedisClient,
    lock_name: str = CLICK_QUEUE_LOCK,
    timeout: float = REDIS_QUEUE_LOCK_TIMEOUT,
) -> Lock:
    return redis.lock(lock_name, timeout=timeout)


def get_cache_lock(
    redis: RedisClient,
    lock_name: str = GLOBAL_CACHE_LOCK,
    timeout: float = REDIS_CACHE_LOCK_TIMEOUT,
) -> Lock:
    return redis.lock(lock_name, timeout=timeout)