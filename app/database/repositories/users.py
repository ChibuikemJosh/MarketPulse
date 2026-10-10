"""Persistence operations for authentication users."""

import logging
from typing import Any

from app.database.connection import db_session

logger = logging.getLogger(__name__)


def get_user_by_id(user_id: int) -> Any | None:
    """Return one user row by ID, or None when it does not exist."""
    try:
        with db_session() as connection:
            row = connection.execute("SELECT id, username, hash, email, auth_provider, provider_id FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None
 
    except Exception:
        logger.error("Failed to load user %s", user_id, exc_info=True)
        raise


def get_user_by_username(username: str) -> Any | None:
    """Return a local user by username."""
    with db_session() as connection:
        row = connection.execute("SELECT id, username, hash, email, auth_provider, provider_id FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

def get_user_by_email(email: str) -> Any | None:
    """Return a user by normalized email."""
    with db_session() as connection:
        row = connection.execute("SELECT id, username, hash, email, auth_provider, provider_id FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_provider(provider: str, provider_id: str) -> Any | None:
    """Return a user by stable external provider identity."""
    with db_session() as connection:
        row = connection.execute("SELECT id, username, hash, email, auth_provider, provider_id FROM users WHERE auth_provider = ? AND provider_id = ?", (provider, provider_id)).fetchone()
        return dict(row) if row else None


def create_local_user(username: str, password_hash: str, email: str | None = None) -> int:
    """Create a local account and return its database ID."""
    with db_session() as connection:
        cursor = connection.execute("INSERT INTO users (username, hash, email, auth_provider) VALUES (?, ?, ?, 'local')", (username, password_hash, email))
        connection.commit()
        return int(cursor.lastrowid)


def create_google_user(username: str, email: str | None, provider_id: str) -> int:
    """Create a Google-backed account without storing a Google password."""
    with db_session() as connection:
        cursor = connection.execute("INSERT INTO users (username, hash, email, auth_provider, provider_id) VALUES (?, '', ?, 'google', ?)", (username, email, provider_id))
        connection.commit()
        return int(cursor.lastrowid)