"""Shared FastAPI dependencies for application services."""

from fastapi import HTTPException, Request

from app.cache.redis import RedisService
from app.services.market_data.models import Instrument
from app.services.market_data.normalization import load_instrument_registry, resolve_instrument
from app.services.market_data.orchestrator import MarketDataOrchestrator


def get_redis(request: Request) -> RedisService:
    """Return the application Redis service."""
    return request.app.state.redis


def get_orchestrator(request: Request) -> MarketDataOrchestrator:
    """Return the shared market-data orchestrator."""
    return request.app.state.market_data


def resolve_requested_instrument(raw_symbol: str) -> Instrument:
    """Resolve a symbol or instrument ID or raise a 404 response."""
    registry = load_instrument_registry()
    for instrument in registry.values():
        if instrument.instrument_id == raw_symbol.upper():
            return instrument
    instrument = resolve_instrument(raw_symbol, registry)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument
