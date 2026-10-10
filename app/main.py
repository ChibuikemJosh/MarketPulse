from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# 1. Get the path of the directory containing this file
BASE_DIR = Path(__file__).resolve().parent

# 2. Point directly to the .env file in the app directory
# (Adjust this path to exactly where your single .env file lives)
env_path = BASE_DIR / ".env" 

from dotenv import load_dotenv
load_dotenv(dotenv_path=env_path, override=True)

from app.cache.redis import RedisService
from app.core import config
from app.database.init import init_db
from app.services.clicks import flush_click_queue
from app.services.trends import refresh_market_cache
from app.services.market_data.normalization import load_instrument_registry
from app.services.market_data.orchestrator import MarketDataOrchestrator
from app.services.market_data.providers.factory import build_default_providers
from app.routers import auth, clicks, data, market, news, pages, search, watchlists
import httpx

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database and Redis service when the application starts.
    init_db()

    redis_service = RedisService()
    client = httpx.AsyncClient(timeout=config.PROVIDER_TIMEOUT_SECONDS)
    app.state.redis = redis_service
    app.state.client = client
    app.state.market_data = MarketDataOrchestrator(build_default_providers(redis_service, client), redis=redis_service)
    app.state.instrument_registry = load_instrument_registry()
    refresh_task = asyncio.create_task(refresh_market_cache(redis_service, client=client))
    yield

    refresh_task.cancel()
    try:
        await refresh_task
    except (asyncio.CancelledError, Exception):
        logger.info("Market cache refresh task stopped")
    await flush_click_queue(redis_service)
    await redis_service.close()
    await client.aclose()

app = FastAPI(title="MarketPulse", version="1.0.0", docs_url="/docs", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY or "marketpulse-dev-secret",
    max_age=config.SESSION_MAX_AGE,
    https_only=config.SESSION_COOKIE_SECURE,
    same_site=config.SESSION_SAME_SITE,
    path="/",
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(pages.router)
app.include_router(search.router)
app.include_router(market.router)
app.include_router(clicks.router)
app.include_router(watchlists.router)
app.include_router(data.router)
app.include_router(news.router)
app.include_router(auth.router)

@app.get("/health", tags=["Health Check"])
async def health():
    # Health check endpoint to verify that the application is running
    return {"status": "success"}