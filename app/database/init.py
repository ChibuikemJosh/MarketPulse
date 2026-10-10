# Module to initialize the database and create necessary tables if they don't exist
import sqlite3
from app.core.config import DB_PATH
from app.database.connection import get_db_connection

import logging

logger = logging.getLogger(__name__)


def init_db():
    try:
        with get_db_connection() as conn:
            # Enable foreign key support in SQLite
            conn.execute("PRAGMA foreign_keys = ON;")

            # Create users table for authentication and user identification
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    hash TEXT NOT NULL,
                    email TEXT,
                    auth_provider TEXT NOT NULL DEFAULT 'local',
                    provider_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            for column, definition in (
                ("email", "TEXT"),
                ("auth_provider", "TEXT NOT NULL DEFAULT 'local'"),
                ("provider_id", "TEXT"),
                ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ):
                try:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
                except Exception:
                    pass
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider ON users(auth_provider, provider_id) WHERE provider_id IS NOT NULL')

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

            conn.commit()
            logger.info("Database initialized successfully at %s", DB_PATH)

    except Exception as e:
        logger.error("Error initializing database: %s", e, exc_info=True)
        raise