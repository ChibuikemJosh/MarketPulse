"""Persistence operations for authentication users."""

import logging
from typing import Any

from app.database.connection import get_db_connection

logger = logging.getLogger(__name__)


def get_user_by_id(user_id: int) -> Any | None:
    """Return one user row by ID, or None when it does not exist."""
    try:
        with get_db_connection() as connection:
            return connection.execute("SELECT id, username, hash FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception:
        logger.error("Failed to load user %s", user_id, exc_info=True)
        raise