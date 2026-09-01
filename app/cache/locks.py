# --- 6. DISTRIBUTED LOCKS ---

from typing import Optional, Dict, Any, Callable, Awaitable

from redis.asyncio.lock import Lock
import asyncio
from app.core import config


def get_queue_lock(self, lock_name: str = "lock:click:queue", timeout: float = config.REDIS_QUEUE_LOCK_TIMEOUT) -> Lock:
    """Returns a distributed queue lock."""
    return self.redis.lock(lock_name, timeout=timeout)

def get_cache_lock(self, lock_name: str = "lock:global:cache", timeout: float = config.REDIS_CACHE_LOCK_TIMEOUT) -> Lock:
    """
    Returns a distributed cache lock instance.
    Ensures multi-step operations on specific cache fields are mutually exclusive.
    """
    return self.redis.lock(lock_name, timeout=timeout)