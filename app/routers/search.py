"""Search API routes."""

from fastapi import APIRouter, Depends, Query, Request

from app.cache.redis import RedisService
from app.routers.dependencies import get_redis
from app.services.search import search_symbols
from app.routers.dependencies import optional_current_user
from app.services.market_data.normalization import load_instrument_registry
from app.core.security import CurrentUser

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search_endpoint(
    request: Request,
    q: str = Query(min_length=1, max_length=100),
    redis: RedisService = Depends(get_redis),
    user: CurrentUser | None = Depends(optional_current_user),
):
    """Return configured and fallback instrument suggestions."""
    registry = getattr(request.app.state, "instrument_registry", None)

    if not registry:
        registry = load_instrument_registry()
        request.app.state.instrument_registry = registry

    return await search_symbols(q, redis, user_id=user.id if user else None, registry=registry)
