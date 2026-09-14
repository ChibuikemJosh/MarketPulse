"""Quote and graph data API routes."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from app.routers.dependencies import get_orchestrator, resolve_requested_instrument
from app.services.market_data.graph import candle_points, line_points
from app.services.market_data.models import ProviderFailure
from app.services.market_data.orchestrator import MarketDataOrchestrator

router = APIRouter(tags=["market-data"])


@router.get("/candles/{instrument_id:path}")
async def candles_endpoint(
    instrument_id: str,
    start: date | None = None,
    end: date | None = None,
    interval: str = Query(default="1d"),
    orchestrator: MarketDataOrchestrator = Depends(get_orchestrator),
):
    """Return normalized OHLCV candles from the provider fallback chain."""
    instrument = resolve_requested_instrument(instrument_id)
    end_date = end or date.today()
    start_date = start or end_date - timedelta(days=365)
    result = await orchestrator.historical_candles(instrument, start_date, end_date, interval)
    if isinstance(result, ProviderFailure):
        return {"status": "error", "error": result.__dict__, "symbol": instrument.symbol}
    return {"status": "ok", "symbol": instrument.symbol, "provider_data": candle_points(result)}


@router.get("/api/graph/{instrument_id:path}")
async def graph_endpoint(
    instrument_id: str,
    mode: str = Query(default="line", pattern="^(line|candle)$"),
    start: date | None = None,
    end: date | None = None,
    interval: str = Query(default="1d"),
    orchestrator: MarketDataOrchestrator = Depends(get_orchestrator),
):
    """Return line or candlestick graph points using the same normalized candles."""
    instrument = resolve_requested_instrument(instrument_id)
    end_date = end or date.today()
    start_date = start or end_date - timedelta(days=365)
    result = await orchestrator.historical_candles(instrument, start_date, end_date, interval)
    if isinstance(result, ProviderFailure):
        return {"status": "error", "error": result.__dict__, "symbol": instrument.symbol, "mode": mode}
    points = line_points(result) if mode == "line" else candle_points(result)
    return {"status": "ok", "symbol": instrument.symbol, "mode": mode, "points": points}


@router.get("/api/quote")
async def quote_endpoint(
    symbol: str,
    orchestrator: MarketDataOrchestrator = Depends(get_orchestrator),
):
    """Return a normalized latest quote for a configured instrument."""
    instrument = resolve_requested_instrument(symbol)
    result = await orchestrator.quote(instrument)
    if isinstance(result, ProviderFailure):
        return {"status": "error", "error": result.__dict__, "symbol": instrument.symbol}
    return {"status": "ok", "symbol": instrument.symbol, "quote": result.__dict__}
