"""FastAPI-rendered page routes."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.cache.redis import RedisService
from app.services.market_data.normalization import resolve_instrument, tradingview_chart_symbol

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/")
async def index(request: Request):
    """Render the dashboard from Redis-cached market trends."""
    redis: RedisService = request.app.state.redis
    scores = await redis.get_trending_scores()
    names = await redis.get_cached_names()
    stocks = [
        {"symbol": symbol, "name": names.get(symbol, symbol), "price_change": float(change)}
        for symbol, change in scores.items()
    ]
    stocks.sort(key=lambda item: abs(item["price_change"]), reverse=True)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"trending_stocks": stocks[:15], "news": [], "user_authenticated": False},
    )


@router.get("/quote")
async def quote_page(request: Request, symbol: str):
    """Render a quote page with an optional TradingView chart symbol."""
    instrument = resolve_instrument(symbol)
    chart_symbol = tradingview_chart_symbol(instrument) if instrument else symbol.upper()
    return templates.TemplateResponse(
        request=request,
        name="quote.html",
        context={"symbol": symbol.upper(), "tradingview_symbol": chart_symbol, "user_authenticated": False},
    )
