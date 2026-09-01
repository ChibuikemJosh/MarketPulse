import sqlite3
from core.config import DATABASE_URL

DB_PATH = DATABASE_URL

def init_db():
    """Initialize database tables if they don't exist.
    Creates 'clicks' table for tracking user interactions and 'users' table for authentication.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        db = conn.cursor()

        # Create users table for authentication and user identification
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hash TEXT NOT NULL
            )
        ''')

        # Create clicks table to track which symbols users interact with (for trending/ranking)
        db.execute('''
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                user_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                   )
        ''')

        # Indexes speed up queries filtering by symbol or user_id
        db.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON clicks(symbol)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_user ON clicks(user_id)')

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Retrieval Error: {e}")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn