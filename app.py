import json
import os
import sqlite3
import threading
import time
import math
import re
from datetime import datetime, timedelta
from collections import deque

# Data and APIs
import pandas as pd
import requests
import yfinance as yf
from tradingview_screener import Query

# Web Framework and Security
from flask import Flask, render_template, jsonify, request, session, flash, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

# Search and Logic
from rapidfuzz import fuzz

# Your Custom Logic
from helpers import get_market_news, get_stock_data


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================
API_LIMIT = {
    "ALPHA_VANTAGE": 25
    }  # Max Alpha Vantage API calls per day (free tier limit)
DB_PATH = 'marketpulse.db'  # SQLite database filename
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # Standard datetime format for database timestamps

# ============================================================================
# GLOBAL CACHES - Thread-safe dictionary caches to minimize database/API calls
# ============================================================================
GLOBAL_WEIGHT_CACHE = {}  # Cache of popularity scores for all symbols (globally aggregated clicks)
USER_SESSION_CACHES = {}  # Cache of user-specific click weights indexed by user_id {user_id: {symbol: weight}}
TRENDING_SCORES = {}  # Cache of price change percentages for symbols {symbol: change_pct}
CACHED_NAMES = {}  # Cache of cleaned company names for symbols {symbol: clean_name}
STATS_CACHE = {
    "ALPHA_VANTAGE": {'api_calls_today': 0,  # Counter for Alpha Vantage API calls made today
                    'last_reset_date': datetime.now().date()}  # Date when counter was last reset
    }

# ============================================================================
# QUEUE & THREAD SYNCHRONIZATION
# ============================================================================
click_queue = deque()  # Queue to batch clicks before writing to database (for performance)

cache_lock = threading.Lock()  # Mutex for protecting access to global caches (thread-safe)
queue_lock = threading.Lock()  # Mutex for protecting access to click_queue (thread-safe)


app = Flask(__name__)


# Initialize Flask-Login and bind it to this Flask app instance.
login_manager = LoginManager()
login_manager.init_app(app)


# Minimal user model required by Flask-Login for session handling.
class User(UserMixin):
    def __init__(self, id):
        self.id = id


# Rehydrate a user object from the session-stored user_id.
@login_manager.user_loader
def load_user(user_id):
    return None


# ============================================================================
# BRAND MAP - Load company symbols and aliases for search functionality
# ============================================================================
try:
    with open('brand_config.json', 'r', encoding='utf-8') as file:
        BRAND_MAP = json.load(file)  # {symbol: [alias1, alias2, ...]} for fuzzy matching
except:
    BRAND_MAP = {}  # Graceful fallback if file not found
    print("Retrieval of Brand_MAP Error")  # Users need to provide brand_config.json

try:
    with open('market_config.json', 'r', encoding='utf-8') as file:
        MARKET_MAP = json.load(file)
except:
    MARKET_MAP = {}  # Graceful fallback if file not found
    print("Retrieval of MARKET_MAP Error")  # Users need to provide market_config.json

# ============================================================================
# API KEYS - Load environment variables for external services
# ============================================================================
try:
    load_dotenv()  # Load from .env file in project root
    ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")  # API key for stock symbol search
except Exception as e:
    ALPHA_VANTAGE_KEY = ""  # Graceful fallback if key not found
    print(f"Retreival of Alpha Vantage API key Error: {e}")


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


init_db()


def get_user_weights(user_id):
    """Retrieve personalized symbol weights for a user based on their click history.
    Uses exponential decay: recent clicks weigh more than old clicks.
    Caches results to avoid repeated database queries.

    Args:
        user_id: User identifier from session

    Returns:
        Dictionary {symbol: weight} representing user's preference for each symbol
    """
    global USER_SESSION_CACHES

    # Return empty dict if no user ID provided (anonymous user)
    if not user_id:
        return {}

    # Check in-memory cache first for performance
    with cache_lock:
        if user_id in USER_SESSION_CACHES:
            return USER_SESSION_CACHES[user_id]

    # Query database for all clicks from this user in past 30 days
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now()
    thirty_days_ago = (now - timedelta(days=30)).strftime(TIME_FORMAT)

    cursor = conn.execute('''
        SELECT symbol, timestamp FROM clicks
        WHERE user_id = ? AND timestamp > ?
    ''', (user_id, thirty_days_ago))

    user_weights = {}

    # Apply exponential decay: weight = 0.8^(days_ago)
    # Example: click from 1 day ago = 0.8^1 = 0.8 weight
    #          click from 10 days ago = 0.8^10 ≈ 0.107 weight (older clicks matter less)
    for symbol, timestamp in cursor:
        timestamp = datetime.strptime(timestamp, TIME_FORMAT)
        weight = 0.8 ** ((now - timestamp).total_seconds() / 86400)  # Convert seconds to days
        user_weights[symbol] = user_weights.get(symbol, 0) + weight  # Accumulate weights for same symbol

    conn.close()

    # Store in cache to avoid querying database again for same user
    with cache_lock:
        USER_SESSION_CACHES[user_id] = user_weights

    return user_weights

def load_global_weights():
    """Aggregate click data across ALL users to determine globally trending symbols.
    Uses logarithmic normalization to prevent a few popular symbols from dominating.
    Called by background thread periodically.
    """
    global GLOBAL_WEIGHT_CACHE
    conn = sqlite3.connect(DB_PATH)

    now = datetime.now()
    # Only consider clicks from past 30 days (older data becomes stale)
    thirty_days_ago = (now - timedelta(days=30)).strftime(TIME_FORMAT)

    # Get all clicks regardless of user
    cursor = conn.execute('''
                          SELECT symbol, timestamp FROM clicks
                          WHERE timestamp > ?
                          ''', (thirty_days_ago,))
    
    symbol_scores = {}  # Aggregate scores for each symbol
    total_weighted_sum = 0  # Total weight across ALL clicks

    # Apply same exponential decay as user weights
    for symbol, timestamp in cursor:
        timestamp = datetime.strptime(timestamp, TIME_FORMAT)
        weight = 0.8 ** ((now - timestamp).total_seconds() / 86400)

        symbol_scores[symbol] = symbol_scores.get(symbol, 0) + weight
        total_weighted_sum += weight