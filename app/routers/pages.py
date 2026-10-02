"""FastAPI-rendered page routes."""

import asyncio
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.cache.redis import RedisService
from app.services.market_data.normalization import load_instrument_registry, resolve_instrument, tradingview_chart_symbol
from app.services.news import get_instrument_news, get_market_news
from app.core.security import get_current_user
from app.database.repositories.watchlists import check_watchlist_item, list_watchlist_items

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/")
async def index(request: Request):
    """Render the dashboard from Redis-cached market trends."""
    redis: RedisService = request.app.state.redis
    scores = await redis.get_trending_scores()
    names = await redis.get_cached_names()
    stocks = []
    for symbol, change in scores.items():
        metadata = await redis.get_trending_metadata(symbol) or {}
        stocks.append({
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "price": metadata.get("price"),
            "change": metadata.get("change"),
            "price_change": metadata.get("change_percent", float(change)),
            "as_of": metadata.get("as_of"),
            "data_status": metadata.get("status", "unavailable"),
        })
    stocks.sort(key=lambda item: abs(item["price_change"]), reverse=True)
    news_page = await get_market_news(redis, 0)
    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"trending_stocks": stocks[:15], "news": news_page["items"], "news_has_more": news_page["has_more"], "news_next_offset": news_page["next_offset"], "user_authenticated": user is not None, "current_user": user},
    )


@router.get("/quote")
async def quote_page(request: Request, symbol: str):
    """Render a quote page with an optional TradingView chart symbol."""
    registry = getattr(request.app.state, "instrument_registry", None) or load_instrument_registry()

    if not getattr(request.app.state, "instrument_registry", None):        
        request.app.state.instrument_registry = registry

    instrument = resolve_instrument(symbol, registry)
    chart_symbol = tradingview_chart_symbol(instrument) if instrument else symbol.upper()
    redis: RedisService = request.app.state.redis
    news_page = await get_instrument_news(instrument.symbol if instrument else symbol, redis, 0)
    user = get_current_user(request)
    quote = None
    orchestrator = getattr(request.app.state, "market_data", None)
    if instrument and orchestrator:
        try:
            result = await asyncio.wait_for(orchestrator.quote(instrument), timeout=3)
            if not hasattr(result, "provider"):
                quote = result
            else:
                metadata = await redis.get_trending_metadata(instrument.symbol) or {}
                quote = {
                    "price": metadata.get("price"),
                    "change": metadata.get("change"),
                    "change_percent": metadata.get("change_percent"),
                    "as_of": metadata.get("as_of"),
                }
        except asyncio.TimeoutError:
            metadata = await redis.get_trending_metadata(instrument.symbol) or {}
            quote = {
                "price": metadata.get("price"),
                "change": metadata.get("change"),
                "change_percent": metadata.get("change_percent"),
                "as_of": metadata.get("as_of"),
            }
    is_watchlisted = False
    if user and instrument:
        is_watchlisted = check_watchlist_item(user.id, instrument.symbol)
    return templates.TemplateResponse(
        request=request,
        name="quote.html",
        context={
            "symbol": symbol.upper(),
            "tradingview_symbol": chart_symbol,
            "instrument": instrument,
            "news": news_page["items"],
            "news_has_more": news_page["has_more"],
            "news_next_offset": news_page["next_offset"],
            "user_authenticated": user is not None,
            "current_user": user,
            "is_watchlisted": is_watchlisted,
            "quote": quote,
        },
    )


@router.get("/watchlist")
async def watchlist_page(request: Request):
    """Render the watchlist shell; data is loaded by the authenticated API."""
    user = get_current_user(request)
    redis: RedisService = request.app.state.redis
    watchlist = []
    if user:
        symbols = list_watchlist_items(user.id)
        names = await redis.get_cached_names()
        trends = await redis.get_trending_scores()
        for item in symbols:
            metadata = await redis.get_trending_metadata(item) or {}
            watchlist.append({
                "symbol": item,
                "name": names.get(item, item),
                "price": metadata.get("price"),
                "change": metadata.get("change"),
                "price_change": metadata.get("change_percent", trends.get(item)),
                "as_of": metadata.get("as_of"),
            })
    return templates.TemplateResponse(
        request=request,
        name="watchlist.html",
        context={"user_authenticated": user is not None, "current_user": user, "watchlist": watchlist, "news": [], "trending_stocks": []},
    )


@router.get("/market-news")
async def market_news_page(request: Request):
    """Render the dedicated mobile-friendly market news page."""
    redis: RedisService = request.app.state.redis
    user = get_current_user(request)
    page = await get_market_news(redis, 0)
    return templates.TemplateResponse(
        request=request,
        name="market_news.html",
        context={"user_authenticated": user is not None, "current_user": user, "news": page["items"], "news_has_more": page["has_more"], "news_next_offset": page["next_offset"]},
    )
