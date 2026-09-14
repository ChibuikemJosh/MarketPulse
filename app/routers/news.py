"""Paginated Finnhub news routes."""

from fastapi import APIRouter, Depends, Query

from app.cache.redis import RedisService
from app.routers.dependencies import get_redis
from app.services.news import get_instrument_news, get_market_news

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/market")
async def market_news(
    offset: int = Query(default=0, ge=0),
    redis: RedisService = Depends(get_redis),
):
    """Return general market news, 15 initially then five per page."""
    return await get_market_news(redis, offset)


@router.get("/instrument/{symbol}")
async def instrument_news(
    symbol: str,
    offset: int = Query(default=0, ge=0),
    redis: RedisService = Depends(get_redis),
):
    """Return seven-day symbol news filtered by ticker and aliases."""
    return await get_instrument_news(symbol, redis, offset)
