from datetime import datetime
import logging
from typing import Optional

import asyncio
import redis.asyncio as aioredis
from redis.asyncio.lock import Lock

import app.cache.locks as Locks
import app.core.config as config
import app.cache.keys as keys

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self, redis_url : str = config.REDIS_URL):
        """
        Initializes the Redis client. 
        The client automatically manages an underlying connection pool.
        """
        
        self.redis: aioredis.Redis = aioredis.from_url(
            redis_url, 
            decode_responses=True,  # Automatically decodes bytes to strings
            max_connections=config.REDIS_MAX_CONNECTIONS      # Tweak based on server scaling
        )
        
        # Redis Key Namespaces
        self.KEY_GLOBAL_WEIGHT = keys.GLOBAL_WEIGHTS  # Using the centralized key from keys.py
        self.KEY_TRENDING_SCORES = keys.TRENDING  # Using the centralized key from keys.py
        self.KEY_CACHED_NAMES = keys.CACHED_NAMES  # Using the centralized key from keys.py
        self.KEY_CLICK_QUEUE = keys.CLICK_QUEUE  # Using the centralized key from keys.py

    async def close(self):
        """ Call this during application shutdown to gracefully clear the pool."""
        logger.info("Closing Redis connection pool...")
        await self.redis.aclose()

    # --- 1. GLOBAL WEIGHT CACHE (Hash) ---
    async def get_global_weight(self, symbol: str) -> Optional[float]:
        val = await self.redis.hget(self.KEY_GLOBAL_WEIGHT, symbol.upper())
        return float(val) if val is not None else None

    async def set_global_weight(self, symbol: str, weight: float):
        await self.redis.hset(self.KEY_GLOBAL_WEIGHT, symbol.upper(), str(weight))

    async def get_global_weights(self) -> dict[str, float]:
        """Return every cached global symbol weight."""
        values = await self.redis.hgetall(self.KEY_GLOBAL_WEIGHT)
        return {symbol: float(weight) for symbol, weight in values.items()}

    async def set_global_weights(self, weights: dict[str, float]) -> None:
        """Replace the global weight hash with the supplied values."""
        async with self.redis.pipeline(transaction=True) as pipeline:
            await pipeline.delete(self.KEY_GLOBAL_WEIGHT)
            if weights:
                await pipeline.hset(
                    self.KEY_GLOBAL_WEIGHT,
                    mapping={symbol.upper(): str(weight) for symbol, weight in weights.items()},
                )
            await pipeline.execute()

    # --- 2. USER WEIGHT CACHE (Dynamic Hashes) ---
    def _user_weight_key(self, user_id: str) -> str:
        return keys.USER_WEIGHTS.format(user_id=user_id)  # Using the centralized key from keys.py

    async def get_user_weight(self, user_id: str, symbol: str) -> Optional[float]:
        key = self._user_weight_key(user_id)
        val = await self.redis.hget(key, symbol.upper())
        return float(val) if val is not None else None

    async def set_user_weight(self, user_id: str, symbol: str, weight: float):
        key = self._user_weight_key(user_id)
        await self.redis.hset(key, symbol.upper(), str(weight))

    async def get_user_weights(self, user_id: str) -> dict[str, float]:
        """Return every cached weight for one user."""
        values = await self.redis.hgetall(self._user_weight_key(user_id))
        return {symbol: float(weight) for symbol, weight in values.items()}

    # --- 3. TRENDING SCORES & CACHED NAMES (Hashes) ---
    async def update_trending_score(self, symbol: str, change_pct: float):
        await self.redis.hset(self.KEY_TRENDING_SCORES, symbol.upper(), str(change_pct))

    async def get_trending_score(self, symbol: str) -> Optional[float]:
        val = await self.redis.hget(self.KEY_TRENDING_SCORES, symbol.upper())
        return float(val) if val is not None else None

    async def get_cached_name(self, symbol: str) -> Optional[str]:
        return await self.redis.hget(self.KEY_CACHED_NAMES, symbol.upper())

    async def set_cached_name(self, symbol: str, clean_name: str):
        await self.redis.hset(self.KEY_CACHED_NAMES, symbol.upper(), clean_name)

    async def get_trending_scores(self) -> dict[str, float]:
        """Return all cached price-change scores."""
        values = await self.redis.hgetall(self.KEY_TRENDING_SCORES)
        return {symbol: float(change) for symbol, change in values.items()}

    async def get_cached_names(self) -> dict[str, str]:
        """Return all cached display names."""
        return await self.redis.hgetall(self.KEY_CACHED_NAMES)

    async def set_trending_scores(self, scores: dict[str, float]) -> None:
        """Replace the trending score hash with the supplied values."""
        async with self.redis.pipeline(transaction=True) as pipeline:
            await pipeline.delete(self.KEY_TRENDING_SCORES)
            if scores:
                await pipeline.hset(
                    self.KEY_TRENDING_SCORES,
                    mapping={symbol.upper(): str(change) for symbol, change in scores.items()},
                )
            await pipeline.execute()

    async def set_cached_names(self, names: dict[str, str]) -> None:
        """Replace the cached names hash with the supplied values."""
        async with self.redis.pipeline(transaction=True) as pipeline:
            await pipeline.delete(self.KEY_CACHED_NAMES)
            if names:
                await pipeline.hset(
                    self.KEY_CACHED_NAMES,
                    mapping={symbol.upper(): clean_name for symbol, clean_name in names.items()},
                )
            await pipeline.execute()

    # --- 4. ATOMIC STATS CACHE (String Counter with Dynamic Date) ---
    async def increment_alpha_vantage_calls(self) -> int:
        """
        Increments daily calls atomically. 
        Uses the format: api:stats:alpha_vantage:calls:YYYY-MM-DD
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        key = keys.API_STATS.format(today_str=today_str)  # Using the centralized key from keys.py
        
        # Increment atomically
        count = await self.redis.incr(key)
        
        # If it's a new key (count == 1), set a 24-hour TTL to self-clean old dates
        if count == 1:
            await self.redis.expire(key, 86400) 
            
        return count

    async def get_alpha_vantage_calls(self) -> int:
        """Return today's Alpha Vantage call count without incrementing it."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        value = await self.redis.get(keys.API_STATS.format(today_str=today_str))
        return int(value) if value is not None else 0

    # --- 5. DOUBLE-ENDED QUEUE (List) ---
    async def push_click_to_queue(self, click_data: str):
        """Pushes an element to the right side of the queue."""
        await self.redis.rpush(self.KEY_CLICK_QUEUE, click_data)

    async def pop_click_from_queue(self) -> Optional[str]:
        """Pops an element from the left side of the queue (FIFO logic)."""
        return await self.redis.lpop(self.KEY_CLICK_QUEUE)

    def get_queue_lock(
            self,
            lock_name: str = keys.CLICK_QUEUE_LOCK,
            timeout: float = config.REDIS_QUEUE_LOCK_TIMEOUT,
        ) -> Lock:

        return Locks.get_queue_lock(self.redis, lock_name=lock_name, timeout=timeout)

    def get_cache_lock(
        self,
        lock_name: str = keys.CLICK_CACHE_LOCK,
        timeout: float = config.REDIS_CACHE_LOCK_TIMEOUT,
    ) -> Lock:

        return Locks.get_cache_lock(self.redis, lock_name=lock_name, timeout=timeout)