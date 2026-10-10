"""Authenticated watchlist API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database.repositories.watchlists import add_watchlist_item, list_watchlist_items, remove_watchlist_item, check_watchlist_item
from app.routers.dependencies import current_user
from app.core.security import CurrentUser

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


class WatchlistRequest(BaseModel):
    """Payload containing a canonical symbol."""

    symbol: str


@router.get("")
@router.get("/")
async def get_watchlist(user: CurrentUser = Depends(current_user)):
    """Return the authenticated user's saved symbols."""
    return {"symbols": list_watchlist_items(user.id)}


@router.get("/status/{symbol}")
async def watchlist_status(symbol: str, user: CurrentUser = Depends(current_user)):
    """Return whether the authenticated user saved one symbol."""
    return {"symbol": symbol.upper(), "saved": check_watchlist_item(user.id, symbol)}


@router.post("", status_code=201)
@router.post("/add", status_code=201)
async def add_watchlist(payload: WatchlistRequest | str, user: CurrentUser = Depends(current_user)):
    """Add one symbol to the authenticated user's watchlist."""
    if isinstance(payload, WatchlistRequest):
        symbol = payload.symbol.strip().upper()
    else:
        symbol = payload.strip().upper()
    
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol must not be empty")
    return {"added": add_watchlist_item(user.id, symbol), "symbol": symbol}


@router.delete("/{symbol}")
async def delete_watchlist(symbol: str, user: CurrentUser = Depends(current_user)):
    """Remove one symbol from the authenticated user's watchlist."""
    return {"removed": remove_watchlist_item(user.id, symbol)}
