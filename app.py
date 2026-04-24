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
    'api_calls_today': 0,  # Counter for Alpha Vantage API calls made today
    'last_reset_date': datetime.now().date()  # Date when counter was last reset
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
    try:
        conn = get_db_connection()
        cur = conn.execute("SELECT id FROM users WHERE id = ?", (int(user_id),))
        row = cur.fetchone()
        conn.close()
        if row:
            return User(str(row["id"]))
    except Exception:
        return None
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

    conn.close()

    # Normalize using logarithmic scale to compress range (prevent overfitting to a few symbols)
    # Formula: log(score+1) / log(total+1) * 100 => normalizes to roughly 0-100 range
    new_weights = {}
    if total_weighted_sum > 0:
        denominator = math.log(total_weighted_sum + 1)
        for symbol, score in symbol_scores.items():
            new_weights[symbol] = (math.log(score + 1)/ denominator) * 100

    # Update global cache used by search results
    with cache_lock:
        GLOBAL_WEIGHT_CACHE = new_weights


def push_to_db():
    """Flush all queued clicks to database in a single batch operation.
    Called when click_queue reaches 10 items or manually.
    """
    batch_to_write = []

    # Extract all queued clicks atomically
    with queue_lock:
        while click_queue:
            batch_to_write.append(click_queue.popleft())

    # No data to write
    if not batch_to_write:
        return None

    # Write all clicks at once using executemany (more efficient than individual inserts)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.executemany('INSERT INTO clicks (symbol, user_id, timestamp) VALUES (?,?,?)', batch_to_write)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Error during push: {e}")


def record_click(symbol, user_id=None):
    """Record a user's click on a symbol. Batches clicks before database write for efficiency.
    Updates in-memory cache immediately, adds click to queue for batch database insertion.

    Args:
        symbol: Stock symbol clicked (e.g., 'AAPL')
        user_id: Optional user ID; if None, click is recorded as anonymous
    """
    global USER_SESSION_CACHES
    now = datetime.now()

    # Update in-memory user cache immediately (instant feedback for search ranking)
    with cache_lock:
        if user_id:
            if user_id not in USER_SESSION_CACHES:
                USER_SESSION_CACHES[user_id] = {}

            USER_SESSION_CACHES[user_id][symbol] = USER_SESSION_CACHES[user_id].get(symbol, 0) + 1.0

    # Queue the click for batch database insertion
    should_flush = False
    with queue_lock:
        click_queue.append((symbol, user_id, now.strftime(TIME_FORMAT)))

        # Batch optimization: flush to database when queue reaches 10 items
        # This reduces database I/O compared to writing on every click
        should_flush = len(click_queue) >= 10

    if should_flush:
        push_to_db()


def can_call_alpha_vantage_api():
    """Check if API call quota is available for today.
    Alpha Vantage free tier allows 25 calls/day; counter resets at midnight UTC.

    Returns:
        bool: True if calls remaining, False if quota exceeded
    """
    today = datetime.now().date()

    with cache_lock:
        # Reset counter if date has changed
        if today > STATS_CACHE["last_reset_date"]:
            STATS_CACHE["api_calls_today"] = 0
            STATS_CACHE["last_reset_date"] = today

        return STATS_CACHE["api_calls_today"] < API_LIMIT["ALPHA_VANTAGE"]
    

    
def fetch_data_from_alpha_vantage_api(query):
    """Search for stock symbols via Alpha Vantage API.
    Only called when internal search (BRAND_MAP) returns insufficient results.
    Respects daily API quota to avoid rate limiting.

    Args:
        query: Search keyword (company name or partial symbol)

    Returns:
        list: Array of matching symbols from API, or None on failure/quota exceeded
    """
    # Don't make API call if daily quota exceeded
    if not can_call_alpha_vantage_api():
        return None

    url = f'https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={query}&apikey={ALPHA_VANTAGE_KEY}'

    try:
        r = requests.get(url, timeout=2)
        r.raise_for_status()
        data = r.json()

        # Check for rate limit message
        if "Note" in data:
            print("Alpha Vantage Limit Reached. Skipping name fetch.")
            return None

        # Extract and return matching symbols
        if "bestMatches" in data and len(data["bestMatches"]) > 0:
            with cache_lock:
                STATS_CACHE["api_calls_today"] += 1  # Increment counter only on successful call
            return data["bestMatches"]
        
    except Exception as e:
        print(f"Alpha Vantage Fetch Error: {e}")
        return None


def save_cache_to_disk():
    """Persist cached company names to brand_config.json.
    Uses atomic write (temp file + rename) to prevent corruption if write fails.
    Called periodically by background thread.
    """
    global CACHED_NAMES
    file_path = 'brand_config.json'

    # Snapshot cache to avoid holding lock during file I/O
    with cache_lock:
        names_snapshot = dict(CACHED_NAMES)

    temp_file = None  # Initialize temp_file variable for cleanup in case of error
    
    try:
        # Load existing file or start fresh
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        else:
            existing_data = {}

        # Merge new names into existing data
        for symbol, name in names_snapshot.items():
            if symbol not in existing_data:
                existing_data[symbol] = [name]
            else:
                if name not in existing_data[symbol]:
                    existing_data[symbol].append(name)  # Insert name to brand

        # Atomic write: write to temp file first, then rename
        # This prevents data loss if process crashes during write
        temp_file = file_path + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=4)

        os.replace(temp_file, file_path)  # Atomic rename (replaces original)

    except Exception as e:
        print(f"Error saving brand_config: {e}")
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)


def clean_stock_name(raw_name):
    """Remove corporate suffixes and junk from company names for display.
    Converts 'Apple Inc.' -> 'Apple' and 'Amazon.com Inc' -> 'Amazon.com'.

    Args:
        raw_name: Company name from yfinance or Alpha Vantage

    Returns:
        str: Cleaned name suitable for display in search results
    """
    if not raw_name:
        return ""

    # List of corporate suffixes to remove
    junk = [
        " Corporation", " Corp", " Inc.", " Inc", " Ltd.", " Ltd",
        " Limited", " Plc", " Group", " Holdings", " Common Stock",
        " Class A", " Class B", " ADR", " Co ", " Co."
    ]

    clean_name = raw_name
    for word in junk:
        # re.escape is smart—it ensures periods like 'Inc.' don't break the regex
        clean_name = re.sub(re.escape(word), '', clean_name, flags=re.IGNORECASE)

    # Remove trailing commas and extra whitespace
    return clean_name.replace(',', '').strip()


def calc_price_change(symbol):
    """Calculate percentage price change from previous market close via yfinance.
    Used for trending scores if tradingview fails to boost symbols with positive momentum.

    Args:
        symbol: Stock symbol (e.g., 'AAPL')

    Returns:
        float: Percentage change (0 if error)
    """
    try:
        ticker = yf.Ticker(symbol)

        data = ticker.history(period="2d")

        latest = data.iloc[-1]
        previous = data.iloc[-2]

        daily_change = ((latest['Close'] - previous['Close']) / previous['Close']) * 100

        return daily_change

    except Exception as e:
        print(f"DEBUG: Error in Calculating Price Change for {symbol}: {e}", flush=True)

    return 0  # Return 0 on any error

def update_trends():
    """Periodic background task: update global weights, price trends, and cached names.
    Called every 10 minutes by background thread.
    Does not return; errors are logged but don't stop execution.
    """
    global TRENDING_SCORES
    new_trends = {}  # New trending scores for all tracked symbols

    # Refresh global weights and flush any queued clicks
    try:
        load_global_weights()
        push_to_db()
    except Exception as e:
        print(f"Background Update Error: {e}", flush=True)

    market_groups = {}
    for original_symbol in BRAND_MAP.keys():
        info = MARKET_MAP.get(original_symbol)
        if info:
            m = info['market']
            if m not in market_groups:
                market_groups[m] = []
            market_groups[m].append(original_symbol)

    try:
        for market_name, symbols in market_groups.items():
            try:
                # Fetch all stocks for this country
                _, df = (Query()
                         .set_markets(market_name)
                         .select('name', 'change', 'description')
                         .limit(5000)
                         .get_scanner_data())

                # Results to dictionary {TradingViewTicker: PercentChange}
                price_results = dict(zip(df['name'], df['change']))
                name_results = dict(zip(df['name'], df['description']))

                for s in symbols:
                    tv_ticker = MARKET_MAP[s]['tv_symbol']
                    change = price_results.get(tv_ticker)

                    if change is not None:
                        new_trends[s] = round(float(change), 2)

                    else:
                        new_trends[s] = calc_price_change(s)

                    final_name = None
                    raw_name = name_results.get(tv_ticker)
                    if raw_name:
                        final_name = clean_stock_name(raw_name)

                    if not final_name:
                        ticker = yf.Ticker(s)
                        info = ticker.info
                        raw_name = info.get('shortName') or info.get('longName')
                        if raw_name:
                            final_name = clean_stock_name(raw_name)

                    if not final_name and can_call_alpha_vantage_api():
                        api_data = fetch_data_from_alpha_vantage_api(s)
                        if api_data:
                            final_name = clean_stock_name(api_data[0]["2. name"])
                            time.sleep(12)

                    if not final_name:
                        # If both APIs fail, just take 'AAPL.TO' and make it 'AAPL'
                        final_name = s.split('.')[0]
                    
                    with cache_lock:
                        CACHED_NAMES[s] = final_name

            except Exception as e:
                print(f"DEBUG: Error updating market {market_name}: {e}", flush=True)
                # Fill missing with 0.0 so the app doesn't crash
                for s in symbols:
                    new_trends[s] = 0.0
    except Exception as e:
        print(f"CRITICAL ERROR IN BATCH UPDATE: {e}", flush=True)

    # Update global trending scores and persist to disk
    with cache_lock:
        TRENDING_SCORES = new_trends

    save_cache_to_disk()


def update_caches():
    """Infinite background loop: refresh all caches every 10 minutes (600 seconds).
    Runs in daemon thread; automatically stops when main app stops.
    """
    while True:
        update_trends()  # Update global weights, trends, and cached names
        time.sleep(600)  # Wait 10 minutes before next refresh


def get_search_results(query, user_weights):
    """Search BRAND_MAP for symbols matching query.
    Combines fuzzy matching with user/global/trending boosts.
    Falls back to Alpha Vantage API if results are sparse.

    Args:
        query: Search string (company name or symbol)
        user_weights: Dict of normalized user preference weights {symbol: weight_0_100}

    Returns:
        list: Up to 8 matching symbols as [{symbol, name}] dicts
    """
    query_upper = query.upper()
    query_lower = query.lower()
    query_length = len(query)

    results = []
    seen_symbols = set()  # Track symbols we've already added to avoid duplicates

    # Thresholds for fuzzy matching (hardcoded intentionally)
    FUZZ_THRESHOLD = 50      # Minimum score to consider during search
    FINAL_THRESHOLD = 60     # Minimum score needed to include in results

    # Trending multiplier: gives more weight to trending scores if query is 2+ chars
    # Short queries (1 char) get lower trending boost to prioritize exact matches
    boost_multiplier = 1.0 if query_length >= 2 else 0.2

    # First pass: search through BRAND_MAP (local symbols)
    for symbol, aliases in BRAND_MAP.items():
        symbol_upper = symbol.upper()

        # Fuzzy matching priority:
        # 1. Exact match? Score = 110 (highest)
        if query_upper == symbol_upper:
            fuzz_score = 110
        # 2. Prefix match or alias contains query? Score = 105 (very high)
        elif symbol_upper.startswith(query_upper) or any(query_lower in a.lower() for a in aliases):
            fuzz_score = 105
        # 3. Fuzzy match on symbol or aliases
        else:
            symbol_score = fuzz.token_set_ratio(query_upper, symbol_upper)
            aliases_score = max([fuzz.token_set_ratio(query_lower, a.lower()) for a in aliases]) if aliases else 0
            fuzz_score = max(symbol_score, aliases_score)

        # Skip if below minimum threshold
        if fuzz_score < FUZZ_THRESHOLD:
            continue

        # Fetch boost factors from caches
        with cache_lock:
            global_weight = GLOBAL_WEIGHT_CACHE.get(symbol, 0)  # Global popularity
            trending_score = min(100, TRENDING_SCORES.get(symbol, 0))  # Price movement (capped at 100)

        # Apply boost multipliers to each component
        local_boost = 0.2 * user_weights.get(symbol, 0)          # User preference (max +20)
        global_boost = 0.1 * global_weight                        # Global popularity (max +10)
        trending_boost = abs(0.1 * trending_score * boost_multiplier)  # Price momentum (max +10, adjusted by query length)

        # Total score = fuzzy match + personalization + trending
        total_score = fuzz_score + local_boost + global_boost + trending_boost

        display_symbol = symbol.split('.')[0]  # Strip exchange suffix (e.g., .TO -> AAPL)

        # Add to results if passes threshold and not duplicate
        if display_symbol not in seen_symbols and total_score >= FINAL_THRESHOLD:
            # Get company name from cache, BRAND_MAP, or fallback to symbol
            display_name = CACHED_NAMES.get(symbol)
            if not display_name:
                aliases_for_symbol = BRAND_MAP.get(symbol, [])
                display_name = aliases_for_symbol[0] if aliases_for_symbol else display_symbol

            results.append({
                    'symbol': display_symbol,
                    'name': display_name,
                    'score': total_score,  # Temporary; removed before response
                    'trend': trending_boost
            })
            seen_symbols.add(display_symbol)

    # Second pass: If results sparse and query long enough, query Alpha Vantage API
    if len(results) < 3 and len(query_lower) > 3:
        try:
            data = fetch_data_from_alpha_vantage_api(query_lower)
            if data:
                for match in data:
                    symbol = match["1. symbol"]
                    display_symbol = symbol.split('.')[0]

                    # Get company name
                    display_name = CACHED_NAMES.get(symbol)
                    if not display_name:
                        aliases_for_symbol = BRAND_MAP.get(symbol, [])
                        display_name = aliases_for_symbol[0] if aliases_for_symbol else display_symbol

                    # Apply same boost logic as above
                    local_boost = 0.2 * user_weights.get(symbol, 0)

                    with cache_lock:
                        global_boost = 0.1 * GLOBAL_WEIGHT_CACHE.get(symbol, 0)
                        trending_boost = abs(0.1 * TRENDING_SCORES.get(symbol, 0) * boost_multiplier)

                    # API results get baseline score of 50 (lower than BRAND_MAP matches)
                    total_score = 50 + local_boost + global_boost + trending_boost

                    if display_symbol not in seen_symbols and total_score >= FINAL_THRESHOLD:
                        results.append({
                            'symbol': display_symbol,
                            'name': display_name,
                            'score': total_score,
                            'trend': trending_boost
                        })
                        seen_symbols.add(display_symbol)

                    if len(results) >= 8:
                        break
        except Exception as e:
            print(f"API Error: {e}")

    # Sort by: score (descending), trend (descending), shortest symbol (ascending)
    # Shortest symbols first if tied (AAPL before AAPL.TO)
    results.sort(key=lambda x: (x['score'], x['trend'], -len(x['symbol'])), reverse=True)

    # Remove temporary scoring fields before returning to client
    for r in results:
        r.pop('score', None)
        r.pop('trend', None)

    return results[:8]  # Return top 8 results


# ============================================================================
# FLASK ROUTES
# ============================================================================


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration endpoint.
    GET: Display registration form.
    POST: Create new user account with username and password (hashed with scrypt).
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Validate input
        if not username or not password or password != confirmation:
            return "Invalid input", 400

        # Hash password using scrypt (stronger than bcrypt)
        hashed_pw = generate_password_hash(password, method='scrypt', salt_length=16)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # Insert new user into database
            cur.execute("INSERT INTO users (username, hash) VALUES(?, ?)", (username, hashed_pw))
            user_id = cur.lastrowid  # Get auto-generated user ID
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            return "Username already exists", 400  # UNIQUE constraint failed

        # Automatically log in the new user
        session["user_id"] = user_id
        # Pre-load user's click weights from database
        get_user_weights(user_id)

        flash("Registered!")
        return redirect("/")

    return render_template("login.html")


@app.route('/search_suggest', methods=["POST", "GET"])
def search_suggest():
    """AJAX endpoint for autocomplete suggestions.
    Takes query param 'q' and returns matching symbols.
    Authenticated users get personalized rankings based on their history.
    Anonymous users can pass weights via query param.

    Returns:
        JSON array of [{symbol, name}] matches
    """
    # Get and normalize query
    data = request.get_json() if request.is_json else {}
    query = data.get('q', '').strip().upper()  # Normalize to uppercase for matching
    if not query:
        return jsonify([])  # Empty query returns empty results

    # Get user ID from session (if logged in)
    user_id = session.get("user_id")

    # Load user weights from database or provided query param
    if not user_id:
        # Anonymous: use the history sent from localStorage
        history = data.get('history', {})
        user_weights = {}
        now = datetime.now()

        for symbol, timestamps in history.items():
            for ts_str in timestamps:
                try:
                    # Parse JS ISO string
                    ts = datetime.fromisoformat(ts_str.replace('Z', ''))
                    # Same logic: weight = 0.8^(days_ago)
                    days_ago = (now - ts).total_seconds() / 86400
                    weight = 0.8 ** days_ago
                    user_weights[symbol] = user_weights.get(symbol, 0) + weight
                except Exception:
                    continue

    else:
        # Authenticated user: load from database
        user_weights = get_user_weights(user_id)

    # Ensure symbols in user_weights have entries in trending/name caches
    for symbol in user_weights.keys():
        if symbol not in TRENDING_SCORES:
            with cache_lock:
                TRENDING_SCORES[symbol] = 0
        if symbol not in CACHED_NAMES:
            with cache_lock:
                CACHED_NAMES[symbol] = symbol.split('.')[0]

    # Normalize user weights: sum to 100 for consistent scaling
    user_total_weight = sum(user_weights.values())
    if user_total_weight > 0:
        for symbol in user_weights:
            # Logarithmic normalization prevents heavily-used symbols from dominating
            user_weights[symbol] = (math.log(user_weights[symbol] + 1) / math.log(user_total_weight + 1)) * 100

    # Get search results and return as JSON
    results = get_search_results(query, user_weights)
    return jsonify(results)


@app.route("/api/trending")
def get_trending_api():
    # Get pagination parameters from the URL
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 15))

    # TRENDING_SCORES is stored as {symbol: price_change}.
    stocks = [
        {
            'symbol': symbol,
            'price_change': price_change,
            'name': CACHED_NAMES.get(symbol, 'Unknown')
        }
        for symbol, price_change in sorted(
            TRENDING_SCORES.items(),
            key=lambda item: item[1],
            reverse=True
        )
    ]

    # Slice the data
    chunk = stocks[offset : offset + limit]

    # If we run out of stocks, we return an empty list
    # (The JS will then decide to loop back or stop)
    return jsonify(chunk)


@app.route('/record_click', methods=['POST'])
def record_click_endpoint():
    """Record a user's click on a stock symbol.
    Used to track user interaction for personalized search rankings.

    Expects JSON: {symbol: "AAPL"}
    Returns: {status: "success" | "error"}
    """
    try:
        data = request.get_json() or {}
        symbol = (data.get('symbol') or '').upper().strip()

        if not symbol:
            return jsonify({"status": "error"}), 400

        user_id = session.get("user_id")  # Get user ID from session (None if anonymous)
        record_click(symbol, user_id)  # Record click in cache and queue for database

        return jsonify({"status": "success"}), 200
    except Exception:
        return jsonify({"status": "error"}), 400


@app.route("/")
def index():
    # 1. Prepare Trending Stocks (Logic from your previous setup)
    trending_stocks = []
    with cache_lock:
        sorted_movers = sorted(TRENDING_SCORES.items(), key=lambda x: abs(x[1]), reverse=True)[:15]
        for symbol, change in sorted_movers:
            trending_stocks.append({
                'symbol': symbol,
                'name': CACHED_NAMES.get(symbol, "Unknown"),
                'price_change': round(change, 2)
            })

    initial_news = get_market_news()

    return render_template("index.html", trending_stocks=trending_stocks, news=initial_news)


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

# Start the background cache update thread (daemon mode: exits when main app exits)
threading.Thread(target=update_caches, daemon=True).start()

# Launch Flask server
# Using port 8080 (common in Codespaces)
if __name__ == "__main__":
    app.run(debug=True, port=8080)