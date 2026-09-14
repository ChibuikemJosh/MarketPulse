from datetime import datetime
import json
from typing import Any
import logging
from typing import Optional

import asyncio
import redis.asyncio as aioredis
from redis.asyncio.lock import Lock

import app.cache.locks as Locks
import app.core.config as config
import app.core.constants as constants
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
        self.KEY_TRENDING_METADATA = keys.TRENDING_METADATA
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
        "Set user weight cache for one user for a specific symbol"
        key = self._user_weight_key(user_id)

        await self.redis.hset(key, symbol.upper(), str(weight))

    async def get_user_weights(self, user_id: str) -> dict[str, float]:
        """Return every cached weight for one user."""
        values = await self.redis.hgetall(self._user_weight_key(user_id))

        return {symbol: float(weight) for symbol, weight in values.items()}

    # --- 3. TRENDING SCORES & CACHED NAMES (Hashes) ---
    async def update_trending_score(self, symbol: str, change_pct: float):
        await self.redis.hset(self.KEY_TRENDING_SCORES, symbol.upper(), str(change_pct))

    async def update_trending_metadata(self, symbol: str, metadata: dict[str, Any]) -> None:
        """Store provider and freshness details for one trend value."""
        await self.redis.hset(self.KEY_TRENDING_METADATA, symbol.upper(), json.dumps(metadata, default=str))

    async def get_trending_metadata(self, symbol: str) -> dict[str, Any] | None:
        """Read provider and freshness details for one trend value."""
        value = await self.redis.hget(self.KEY_TRENDING_METADATA, symbol.upper())
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

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
        today_str = datetime.now().strftime(constants.DATE_FORMAT)
        key = keys.API_STATS.format(today_str=today_str)  # Using the centralized key from keys.py
        
        # Increment atomically
        count = await self.redis.incr(key)
        
        # If it's a new key (count == 1), set a 24-hour TTL to self-clean old dates
        if count == 1:
            await self.redis.expire(key, config.ALPHAVANTAGE_RATE_LIMIT_TTL_SECONDS) 
            
        return count

    async def get_alpha_vantage_calls(self) -> int:
        """Return today's Alpha Vantage call count without incrementing it."""
        today_str = datetime.now().strftime(constants.DATE_FORMAT)
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

    def market_cache_key(
        self,
        operation: str,
        instrument_id: str,
        provider: str,
        interval: str = "",
        start: str = "",
        end: str = "",
    ) -> str:
        """Build a cache key that cannot mix providers or date ranges."""
        return keys.MARKET_CACHE.format(
            operation=operation,
            instrument_id=instrument_id,
            provider=provider,
            interval=interval,
            start=start,
            end=end,
        )

    async def get_market_cache(self, key: str) -> dict[str, Any] | None:
        """Read a serialized market-data cache record."""
        value = await self.redis.get(key)
        if value is None:
            return None
        try:
            record = json.loads(value)
            return record if isinstance(record, dict) else None
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed Redis market cache record: %s", key)
            return None

    async def set_market_cache(self, key: str, record: dict[str, Any], ttl: int) -> None:
        """Write a market-data cache record with an explicit freshness TTL."""
        await self.redis.set(key, json.dumps(record, default=str), ex=ttl)

    async def reserve_provider_quota(self, provider: str, period: str, limit: int, ttl: int) -> bool:
        """Atomically reserve one provider request slot for a period."""
        key = keys.PROVIDER_QUOTA.format(provider=provider, period=period)
        script = """
        local current = redis.call('GET', KEYS[1])
        if not current then current = 0 else current = tonumber(current) end
        if current >= tonumber(ARGV[1]) then return 0 end
        local next_value = redis.call('INCR', KEYS[1])
        if next_value == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
        return 1
        """
        result = await self.redis.eval(script, 1, key, limit, ttl)
        return bool(result)

    async def mark_provider_failure(self, provider: str, ttl: int | None = None) -> None:
        """Open a provider circuit for the configured cooldown period."""
        await self.redis.set(
            keys.PROVIDER_CIRCUIT.format(provider=provider),
            "open",
            ex=ttl or config.PROVIDER_CIRCUIT_BREAKER_SECONDS,
        )

    async def provider_is_open(self, provider: str) -> bool:
        """Return whether a provider circuit is currently open."""
        return await self.redis.exists(keys.PROVIDER_CIRCUIT.format(provider=provider)) == 1

    def get_refresh_lock(self) -> Lock:
        """Return the distributed lock used by the market refresh worker."""
        return self.redis.lock(keys.REFRESH_LEADER_LOCK, timeout=config.MARKET_REFRESH_LOCK_SECONDS)