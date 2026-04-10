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

login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id):
        self.id = id