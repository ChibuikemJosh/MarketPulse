"""Market updates API routes."""

from fastapi import APIRouter, Depends, Query

from app.cache.redis import RedisService
from app.routers.dependencies import get_redis
from app.services.news import get_market_news

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/market-updates")
@router.get("/dashboard-updates")
async def market_updates(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=15, ge=1, le=100),
    redis: RedisService = Depends(get_redis),
):
    """Return paginated cached trends for the dashboard."""
    scores = await redis.get_trending_scores()
    names = await redis.get_cached_names()
    stocks = [
        {"symbol": symbol, "name": names.get(symbol, symbol), "price_change": round(float(change), 2)}
        for symbol, change in scores.items()
    ]
    stocks.sort(key=lambda item: abs(item["price_change"]), reverse=True)
    news_page = await get_market_news(redis, offset)
    return {"stocks": stocks[offset:offset + limit], "news": news_page["items"], "news_has_more": news_page["has_more"], "news_next_offset": news_page["next_offset"]}
