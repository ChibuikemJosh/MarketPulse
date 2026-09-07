from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI

from app.cache.redis import RedisService
from app.database.init import init_db
from app.services.clicks import flush_click_queue
from app.services.trends import refresh_market_cache

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database and Redis service when the application starts.
    init_db()

    redis_service = RedisService()
    app.state.redis = redis_service
    refresh_task = asyncio.create_task(refresh_market_cache(redis_service))
    yield

    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        logger.info("Market cache refresh task stopped")
    await flush_click_queue(redis_service)
    await redis_service.close()

app = FastAPI(title="MarketPulse", version="1.0.0", docs_url="/docs", lifespan=lifespan)

@app.get("/", tags=["Health Check"])
async def health():
    # Health check endpoint to verify that the application is running
    return {"status": "success"}