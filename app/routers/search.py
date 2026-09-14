"""Search API routes."""

from fastapi import APIRouter, Depends, Query

from app.cache.redis import RedisService
from app.routers.dependencies import get_redis
from app.services.search import search_symbols

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search_endpoint(
    q: str = Query(min_length=1, max_length=100),
    user_id: str | None = None,
    redis: RedisService = Depends(get_redis),
):
    """Return configured and fallback instrument suggestions."""
    return await search_symbols(q, redis, user_id=user_id)
