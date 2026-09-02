from redis.asyncio import Redis as RedisClient
from redis.asyncio.lock import Lock

from app.core import config
from app.cache import keys

def get_queue_lock(
    redis: RedisClient,
    lock_name: str = keys.CLICK_QUEUE_LOCK,
    timeout: float = config.REDIS_QUEUE_LOCK_TIMEOUT,
) -> Lock:
    return redis.lock(lock_name, timeout=timeout)


def get_cache_lock(
    redis: RedisClient,
    lock_name: str = keys.GLOBAL_CACHE_LOCK,
    timeout: float = config.REDIS_CACHE_LOCK_TIMEOUT,
) -> Lock:
    return redis.lock(lock_name, timeout=timeout)