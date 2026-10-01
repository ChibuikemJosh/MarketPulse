"""Persistence operations for authenticated watchlists."""

import logging
import sqlite3

from app.database.connection import db_session

logger = logging.getLogger(__name__)


def add_watchlist_item(user_id: int, symbol: str) -> bool:
    """Save a symbol for a user, returning false when it already exists."""
    try:
        with db_session() as connection:
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
        with db_session() as connection:
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
        with db_session() as connection:
            rows = connection.execute(
                "SELECT symbol FROM watchlists WHERE user_id = ? ORDER BY created_at, id",
                (user_id,),
            ).fetchall()
            symbols = [row["symbol"] for row in rows]

        return symbols

    except Exception:
        logger.error("Failed to list user %s watchlist", user_id, exc_info=True)
        raise

def check_watchlist_item(user_id: int, symbol: str) -> bool:
    """Return True if a symbol is on the user's watchlist, otherwise False.
    
    Optimized for single-item checks using an index-backed EXISTS query.
    """
    try:
        with db_session() as connection:
            row = connection.execute(
                "SELECT 1 FROM watchlists WHERE user_id = ? AND symbol = ? LIMIT 1",
                (user_id, symbol.upper()),
            ).fetchone()
            
        return row is not None
    except Exception:
        logger.error("Failed to check watchlist status for symbol %s and user %s", symbol, user_id, exc_info=True)
        raise
