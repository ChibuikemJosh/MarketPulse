"""Quote and graph data API routes."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from app.routers.dependencies import get_orchestrator, resolve_requested_instrument
from app.services.market_data.graph import candle_points, line_points
from app.services.market_data.chart_config import CHART_RANGES, calculate_date_range, get_allowed_intervals, get_default_interval, get_chart_range, resolve_interval
from app.services.market_data.models import ProviderFailure
from app.services.market_data.orchestrator import MarketDataOrchestrator

router = APIRouter(tags=["market-data"])


@router.get("/api/chart-config")
async def chart_config_endpoint():
    """Return backend-owned chart ranges and interval choices for the UI."""
    return {
        "ranges": {
            key: {
                "default_interval": chart_range.default_interval,
                "allowed_intervals": list(chart_range.allowed_intervals),
            }
            for key, chart_range in CHART_RANGES.items()
        }
    }


@router.get("/candles/{instrument_id:path}")
async def candles_endpoint(
    instrument_id: str,
    start: date | None = None,
    end: date | None = None,
    range_key: str = Query(default="1y", alias="range"),
    interval: str | None = None,
    orchestrator: MarketDataOrchestrator = Depends(get_orchestrator),
):
    """Return normalized OHLCV candles from the provider fallback chain."""
    instrument = resolve_requested_instrument(instrument_id)
    chart_range = get_chart_range(range_key)
    calculated_start, calculated_end = calculate_date_range(chart_range.key, end)
    end_date = end or calculated_end
    start_date = start or calculated_start or date(1970, 1, 1)
    selected_interval = resolve_interval(chart_range.key, interval)
    result = await orchestrator.historical_candles(instrument, start_date, end_date, selected_interval)
    if isinstance(result, ProviderFailure):
        return {"status": "error", "error": result.__dict__, "symbol": instrument.symbol}
    return {"status": "ok", "symbol": instrument.symbol, "range": chart_range.key, "interval": selected_interval, "default_interval": chart_range.default_interval, "available_intervals": get_allowed_intervals(chart_range.key), "provider_data": candle_points(result)}


@router.get("/api/graph/{instrument_id:path}")
async def graph_endpoint(
    instrument_id: str,
    mode: str = Query(default="line", pattern="^(line|candle)$"),
    range_key: str = Query(default="1y", alias="range"),
    start: date | None = None,
    end: date | None = None,
    interval: str | None = None,
    orchestrator: MarketDataOrchestrator = Depends(get_orchestrator),
):
    """Return line or candlestick graph points using the same normalized candles."""
    instrument = resolve_requested_instrument(instrument_id)
    chart_range = get_chart_range(range_key)
    calculated_start, calculated_end = calculate_date_range(chart_range.key, end)
    end_date = end or calculated_end
    start_date = start or calculated_start or date(1970, 1, 1)
    selected_interval = resolve_interval(chart_range.key, interval)
    result = await orchestrator.historical_candles(instrument, start_date, end_date, selected_interval)
    if isinstance(result, ProviderFailure):
        return {"status": "error", "error": result.__dict__, "symbol": instrument.symbol, "range": chart_range.key, "interval": selected_interval, "default_interval": chart_range.default_interval, "available_intervals": get_allowed_intervals(chart_range.key), "mode": mode}
    points = line_points(result) if mode == "line" else candle_points(result)
    return {"status": "ok", "symbol": instrument.symbol, "range": chart_range.key, "interval": selected_interval, "default_interval": chart_range.default_interval, "available_intervals": get_allowed_intervals(chart_range.key), "mode": mode, "points": points}


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
