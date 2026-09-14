from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.cache.redis import RedisService
from app.database.init import init_db
from app.services.clicks import flush_click_queue
from app.services.trends import refresh_market_cache
from app.services.market_data.orchestrator import MarketDataOrchestrator
from app.services.market_data.providers.factory import build_default_providers
from app.routers import clicks, data, market, news, pages, search, watchlists

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database and Redis service when the application starts.
    init_db()

    redis_service = RedisService()
    app.state.redis = redis_service
    app.state.market_data = MarketDataOrchestrator(build_default_providers(redis_service), redis=redis_service)
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
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(pages.router)
app.include_router(search.router)
app.include_router(market.router)
app.include_router(clicks.router)
app.include_router(watchlists.router)
app.include_router(data.router)
app.include_router(news.router)

@app.get("/health", tags=["Health Check"])
async def health():
    # Health check endpoint to verify that the application is running
    return {"status": "success"}