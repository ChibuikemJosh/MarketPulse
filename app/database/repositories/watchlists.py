"""Persistence operations for authenticated watchlists."""

import logging

from app.database.connection import get_db_connection

logger = logging.getLogger(__name__)


def add_watchlist_item(user_id: int, symbol: str) -> bool:
    """Save a symbol for a user, returning false when it already exists."""
    try:
        with get_db_connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO watchlists (user_id, symbol) VALUES (?, ?)",
                (user_id, symbol.upper()),
            )
            connection.commit()
            return cursor.rowcount == 1
    except Exception:
        logger.error("Failed to add %s to user %s watchlist", symbol, user_id, exc_info=True)
        raise


def remove_watchlist_item(user_id: int, symbol: str) -> bool:
    """Remove a symbol from a user's watchlist."""
    try:
        with get_db_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM watchlists WHERE user_id = ? AND symbol = ?",
                (user_id, symbol.upper()),
            )
            connection.commit()
            return cursor.rowcount == 1
    except Exception:
        logger.error("Failed to remove %s from user %s watchlist", symbol, user_id, exc_info=True)
        raise


def list_watchlist_items(user_id: int) -> list[str]:
    """Return a user's saved symbols in insertion order."""
    try:
        with get_db_connection() as connection:
            rows = connection.execute(
                "SELECT symbol FROM watchlists WHERE user_id = ? ORDER BY created_at, id",
                (user_id,),
            ).fetchall()
        return [row["symbol"] for row in rows]
    except Exception:
        logger.error("Failed to list user %s watchlist", user_id, exc_info=True)
        raise
