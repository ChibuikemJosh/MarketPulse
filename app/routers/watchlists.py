"""Authenticated watchlist API routes."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.database.repositories.watchlists import add_watchlist_item, list_watchlist_items, remove_watchlist_item

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


class WatchlistRequest(BaseModel):
    """Payload containing a canonical symbol."""

    symbol: str


def _user_id(header: str | None) -> int:
    """Extract the temporary authenticated user header used until auth routes exist."""
    try:
        if header is None:
            raise ValueError
        return int(header)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Authentication required") from error


@router.get("")
def get_watchlist(x_user_id: str | None = Header(default=None)):
    """Return the authenticated user's saved symbols."""
    return {"symbols": list_watchlist_items(_user_id(x_user_id))}


@router.post("", status_code=201)
def add_watchlist(payload: WatchlistRequest, x_user_id: str | None = Header(default=None)):
    """Add one symbol to the authenticated user's watchlist."""
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol must not be empty")
    return {"added": add_watchlist_item(_user_id(x_user_id), symbol), "symbol": symbol}


@router.delete("/{symbol}")
def delete_watchlist(symbol: str, x_user_id: str | None = Header(default=None)):
    """Remove one symbol from the authenticated user's watchlist."""
    return {"removed": remove_watchlist_item(_user_id(x_user_id), symbol)}
