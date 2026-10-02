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
    stocks = []
    for symbol, change in scores.items():
        metadata = await redis.get_trending_metadata(symbol) or {}
        percentage = metadata.get("change_percent")
        if percentage is None:
            percentage = change
        stocks.append({
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "price": metadata.get("price"),
            "change": metadata.get("change"),
            "price_change": round(float(percentage), 2),
            "as_of": metadata.get("as_of"),
        })
    stocks.sort(key=lambda item: abs(item["price_change"]), reverse=True)

    return {"stocks": stocks[offset:offset + limit]}
