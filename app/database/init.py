# Module to initialize the database and create necessary tables if they don't exist

from app.core.config import DB_PATH
from app.database.connection import get_db_connection

import logging

logger = logging.getLogger(__name__)

def init_db():
    try:
        with get_db_connection() as conn:

            # Create users table for authentication and user identification
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hash TEXT NOT NULL
                )
            ''')

            # Create clicks table to track which symbols users interact with (for trending/ranking)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    user_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
            ''')

            # Indexes speed up queries filtering by symbol or user_id
            conn.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON clicks(symbol)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_user ON clicks(user_id)')

            # Watchlists belong to authenticated users and are unique per symbol.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS watchlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, symbol),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlists(user_id)')

            logger.info("Database initialized successfully at %s", DB_PATH)

            conn.commit()

    except Exception as e:
        logger.error("Error initializing database: %s", e, exc_info=True)