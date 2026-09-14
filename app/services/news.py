"""Finnhub market and instrument news services."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any

import finnhub

from app.cache.redis import RedisService
from app.config.loader import load_brand_map
from app.core.config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)
NEWS_CACHE_TTL = 300
GENERAL_INITIAL_LIMIT = 15
PAGE_SIZE = 5

_STRONG = ("stock", "market", "trading", "earnings", "dividend", "ipo", "acquisition", "merger", "profit", "revenue", "analyst", "securities", "etf", "nasdaq", "dow", "volatility", "upgrade", "downgrade", "buyback", "share", "portfolio", "investment", "investor", "fund")
_WEAK = ("company", "ceo", "cfo", "growth", "economy", "recession", "inflation", "interest rate", "fed", "wall street", "bear market", "bull market", "crypto", "bitcoin", "blockchain", "fintech", "bond", "currency", "commodities", "oil", "gold", "startup", "sector", "bullish", "bearish", "price target", "quarterly", "annual report")
_IRRELEVANT = ("sports", "nfl", "nba", "soccer", "football", "celebrity", "royal", "scandal", "arrest", "suicide", "death", "weather", "hurricane", "disease", "pandemic", "health", "covid", "virus")


def _score(article: dict[str, Any]) -> int:
    """Score an article using the legacy finance relevance policy."""
    text = f"{article.get('headline', '')} {article.get('summary', '')}".lower()
    irrelevant = any(re.search(fr"\b{re.escape(word)}\b", text) for word in _IRRELEVANT)
    strong = any(re.search(fr"\b{re.escape(word)}\b", text) for word in _STRONG)
    weak = any(re.search(fr"\b{re.escape(word)}\b", text) for word in _WEAK)
    if strong:
        return 1 if irrelevant else 2
    if weak and not irrelevant:
        return 1
    return 0


def _client() -> finnhub.Client | None:
    """Create a Finnhub client only when the key is configured."""
    return finnhub.Client(api_key=FINNHUB_API_KEY) if FINNHUB_API_KEY else None


def _fetch_general() -> list[dict[str, Any]]:
    client = _client()
    return client.general_news("general", min_id=0) if client else []


def _fetch_company(symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    client = _client()
    return client.company_news(symbol.upper(), _from=start, to=end) if client else []


def _normalize(article: dict[str, Any]) -> dict[str, Any]:
    """Return only frontend-safe, stable news fields."""
    return {
        "id": article.get("id"),
        "headline": article.get("headline", ""),
        "summary": article.get("summary", ""),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "datetime": article.get("datetime"),
        "image": article.get("image", ""),
    }


async def get_market_news(redis: RedisService, offset: int = 0) -> dict[str, Any]:
    """Return 15 general news items initially and five items per later page."""
    cache_key = redis.market_cache_key("news-general", "market", "finnhub")
    try:
        cached = await redis.get_market_cache(cache_key)
        if cached is None:
            articles = await asyncio.to_thread(_fetch_general)
            filtered = [article for article in articles if _score(article) > 0]
            filtered.sort(key=lambda article: (_score(article), article.get("datetime", 0)), reverse=True)
            cached = {"provider": "finnhub", "fetched_at": datetime.now(timezone.utc).isoformat(), "data": [_normalize(article) for article in filtered]}
            await redis.set_market_cache(cache_key, cached, NEWS_CACHE_TTL)
        articles = cached.get("data", [])
        limit = GENERAL_INITIAL_LIMIT if offset == 0 else PAGE_SIZE
        page = articles[offset:offset + limit]
        return {"items": page, "offset": offset, "has_more": offset + len(page) < len(articles), "next_offset": offset + len(page)}
    except Exception:
        logger.error("Failed to load general market news", exc_info=True)
        return {"items": [], "offset": offset, "has_more": False, "next_offset": offset, "error": "News is temporarily unavailable"}


async def get_instrument_news(symbol: str, redis: RedisService, offset: int = 0) -> dict[str, Any]:
    """Return five paginated company-news items matched by symbol and aliases."""
    brand_map = load_brand_map()
    aliases = brand_map.get(symbol.upper(), [])
    keywords = [symbol.upper(), *(str(alias) for alias in aliases)]
    pattern = re.compile(fr"(?<!\w)({'|'.join(re.escape(keyword) for keyword in keywords if keyword)})(?!\w)", re.IGNORECASE)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    cache_key = redis.market_cache_key("news-instrument", symbol.upper(), "finnhub", start=start.date().isoformat(), end=end.date().isoformat())
    try:
        cached = await redis.get_market_cache(cache_key)
        if cached is None:
            articles = await asyncio.to_thread(_fetch_company, symbol, start.date().isoformat(), end.date().isoformat())
            filtered = [article for article in articles if pattern.search(f"{article.get('headline', '')} {article.get('summary', '')}")]
            cached = {"provider": "finnhub", "fetched_at": datetime.now(timezone.utc).isoformat(), "data": [_normalize(article) for article in filtered]}
            await redis.set_market_cache(cache_key, cached, NEWS_CACHE_TTL)
        articles = cached.get("data", [])
        page = articles[offset:offset + PAGE_SIZE]
        return {"items": page, "symbol": symbol.upper(), "offset": offset, "has_more": offset + len(page) < len(articles), "next_offset": offset + len(page)}
    except Exception:
        logger.error("Failed to load news for %s", symbol, exc_info=True)
        return {"items": [], "symbol": symbol.upper(), "offset": offset, "has_more": False, "next_offset": offset, "error": "Instrument news is temporarily unavailable"}
