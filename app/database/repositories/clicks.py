"""Persistence operations for click analytics."""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Optional

from app.core.constants import TIME_FORMAT
from app.database.connection import get_db_connection
from app.models.click import ClickRecord

logger = logging.getLogger(__name__)


def insert_clicks(records: Iterable[ClickRecord]) -> int:
    """Insert a batch of click records and return the number written.

    Args:
        records: Click records already normalized by the click service.

    Returns:
        The number of records inserted.

    Raises:
        sqlite3.Error: If the database cannot write the batch.
    """
    values = [
        (record.symbol, record.user_id, record.timestamp.strftime(TIME_FORMAT))
        for record in records
    ]
    if not values:
        return 0

    try:
        with get_db_connection() as connection:
            connection.executemany(
                "INSERT INTO clicks (symbol, user_id, timestamp) VALUES (?, ?, ?)",
                values,
            )
            connection.commit()
        return len(values)
    except Exception:
        logger.error("Failed to persist %d click records", len(values), exc_info=True)
        raise


def get_clicks_since(since: datetime, user_id: Optional[str] = None) -> list[tuple[str, str]]:
    """Load recent click symbols and timestamps, optionally for one user.

    Args:
        since: Only clicks newer than this timestamp are returned.
        user_id: Optional user identifier used to filter the query.

    Returns:
        Pairs of symbol and database timestamp string.
    """
    try:
        with get_db_connection() as connection:
            if user_id is None:
                rows = connection.execute(
                    "SELECT symbol, timestamp FROM clicks WHERE timestamp > ?",
                    (since.strftime(TIME_FORMAT),),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT symbol, timestamp FROM clicks "
                    "WHERE user_id = ? AND timestamp > ?",
                    (user_id, since.strftime(TIME_FORMAT)),
                ).fetchall()
        return [(row["symbol"], row["timestamp"]) for row in rows]
    except Exception:
        logger.error("Failed to load click history", exc_info=True)
        raise
