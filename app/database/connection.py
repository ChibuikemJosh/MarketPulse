# Database connection module for the MarketPulse application.

import sqlite3
from contextlib import contextmanager
from app.core.config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    return conn

@contextmanager
def db_session():
    """A convenient context manager to automatically close connections after use."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()