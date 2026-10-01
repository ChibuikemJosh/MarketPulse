import sys
from os import getenv

# Core configuration for the MarketPulse application

# --- CRITICAL PRODUCTION SAFEGUARD ---
# If someone imports config before environment variables are loaded, warn them instantly in development
if not getenv("SECRET_KEY") and not getenv("REDIS_URL") and "pytest" not in sys.modules:
    import warnings
    warnings.warn(
        "core.config initialized before environment variables were populated. "
        "Ensure load_dotenv() runs at the absolute top of your main entry point file.",
        RuntimeWarning
    )

REDIS_URL = getenv("REDIS_URL") or "redis://localhost:6379"

DATABASE_URL = getenv("DATABASE_URL") or "sqlite:///./marketpulse.db"
DB_PATH = getenv("DB_PATH") or "marketpulse.db"

SECRET_KEY = getenv("SECRET_KEY") or ""
GOOGLE_CLIENT_ID = getenv("GOOGLE_CLIENT_ID") or ""
GOOGLE_CLIENT_SECRET = getenv("GOOGLE_CLIENT_SECRET") or ""
GOOGLE_REDIRECT_URI = getenv("GOOGLE_REDIRECT_URI") or "http://localhost:8000/auth/google/callback"

SESSION_COOKIE_SECURE = getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_SAME_SITE = getenv("SESSION_SAME_SITE", "lax").lower()
SESSION_MAX_AGE = int(getenv("SESSION_MAX_AGE", "604800"))

ALPHA_VANTAGE_API_KEY = getenv("ALPHA_VANTAGE_API_KEY") or ""
FINNHUB_API_KEY = getenv("FINNHUB_API_KEY") or ""
GEMINI_API_KEY = getenv("GEMINI_API_KEY") or ""
MASSIVE_API_KEY = getenv("MASSIVE_API_KEY") or getenv("POLYGON_API_KEY") or ""
TIINGO_API_KEY = getenv("TIINGO_API_KEY") or ""

PROVIDER_ENABLED = {
    "tradingview": True,
    "yfinance": True,
    "massive": bool(MASSIVE_API_KEY),
    "tiingo": bool(TIINGO_API_KEY),
}
PROVIDER_TIMEOUT_SECONDS = 10.0
PROVIDER_RETRY_COUNT = 5
ALPHAVANTAGE_RATE_LIMIT_TTL_SECONDS = 86400
PROVIDER_CACHE_TTL_SECONDS = 300
HISTORICAL_CACHE_TTL_SECONDS = 3600
PROVIDER_CIRCUIT_BREAKER_SECONDS = 30
MARKET_REFRESH_LOCK_SECONDS = 540
MARKET_REFRESH_CONCURRENCY = 8
PROVIDER_RATE_LIMITS = {
    "alpha_vantage_daily": 25,
    "massive_per_minute": 5,
}

API_LIMITS = {
    "ALPHA_VANTAGE": 25
}  # Max Alpha Vantage API calls per day (free tier limit)

REDIS_MAX_CONNECTIONS = 20
REDIS_QUEUE_LOCK_TIMEOUT = 10  # seconds
REDIS_CACHE_LOCK_TIMEOUT = 5  # seconds

DEBUG = True