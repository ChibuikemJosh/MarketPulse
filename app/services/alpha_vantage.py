"""Alpha Vantage symbol-search integration with Redis quota tracking."""

import asyncio
import logging
from typing import Any

import requests

from app.cache.redis import RedisService
from app.core.config import ALPHA_VANTAGE_API_KEY

logger = logging.getLogger(__name__)
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


async def fetch_symbol_matches(query: str, redis: RedisService) -> list[dict[str, Any]]:
    """Fetch symbol matches when the daily Alpha Vantage quota permits it.

    Args:
        query: Company name or partial ticker to search.
        redis: Application Redis service used for the quota counter.

    Returns:
        Alpha Vantage match dictionaries, or an empty list on failure.
    """
    if not ALPHA_VANTAGE_API_KEY or not await redis.reserve_provider_quota(
        "alpha_vantage",
        "daily",
        25,
        86400,
    ):
        return []
    try:
        response = await asyncio.to_thread(
            requests.get,
            ALPHA_VANTAGE_URL,
            params={"function": "SYMBOL_SEARCH", "keywords": query, "apikey": ALPHA_VANTAGE_API_KEY},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if "Note" in data or "Information" in data:
            logger.warning("Alpha Vantage returned a rate-limit response")
            return []
        matches = data.get("bestMatches", [])
        return matches
    except (requests.RequestException, ValueError, TypeError):
        logger.error("Alpha Vantage search failed for %r", query, exc_info=True)
        return []
