"""Click analytics API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.cache.redis import RedisService
from app.routers.dependencies import get_redis
from app.services.clicks import record_click

router = APIRouter(prefix="/api", tags=["clicks"])


class ClickRequest(BaseModel):
    """Payload for one stock interaction."""

    symbol: str


@router.post("/clicks", status_code=202)
async def click_endpoint(payload: ClickRequest, redis: RedisService = Depends(get_redis)):
    """Queue an anonymous or authenticated click for ranking analytics."""
    try:
        await record_click(payload.symbol, None, redis)
        return {"status": "accepted"}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
