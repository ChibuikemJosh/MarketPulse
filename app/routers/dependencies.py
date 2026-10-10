"""Shared FastAPI dependencies for application services."""

from fastapi import HTTPException, Request

from app.cache.redis import RedisService
from app.services.market_data.models import Instrument
from app.services.market_data.normalization import load_instrument_registry, resolve_instrument
from app.services.market_data.orchestrator import MarketDataOrchestrator
from app.core.security import CurrentUser, get_current_user, require_current_user


def get_redis(request: Request) -> RedisService:
    """Return the application Redis service."""
    return request.app.state.redis


def get_orchestrator(request: Request) -> MarketDataOrchestrator:
    """Return the shared market-data orchestrator."""
    return request.app.state.market_data


def optional_current_user(request: Request) -> CurrentUser | None:
    """Return the session user or None for an anonymous visitor."""
    return get_current_user(request)


def current_user(request: Request) -> CurrentUser:
    """Require a session user for protected API dependencies."""
    return require_current_user(request)


def resolve_requested_instrument(request:Request, raw_symbol: str) -> Instrument:
    """Resolve a symbol or instrument ID or raise a 404 response."""
    # Prefer pulling the registry from app.state memory if you attach it during startup in main.py
    registry = getattr(request.app.state, "instrument_registry", None)
    
    if registry is None:
        # Fallback to standard loading if state isn't initialized yet
        registry = load_instrument_registry()
        # Store the loaded registry in app.state for future use
        request.app.state.instrument_registry = registry

    for instrument in registry.values():
        if instrument.instrument_id == raw_symbol.upper():
            return instrument
    instrument = resolve_instrument(raw_symbol, registry)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument
