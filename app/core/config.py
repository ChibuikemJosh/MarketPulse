# Core configuration for the MarketPulse application

REDIS_URL = "redis://localhost:6379"
DATABASE_URL = "sqlite:///./marketpulse.db"
SECRET_KEY = "your-secret-key-here"
ALPHA_VANTAGE_API_KEY = ""
FINNHUB_API_KEY = ""
GEMINI_API_KEY = ""
API_LIMITS = {
    "ALPHA_VANTAGE": 25
}  # Max Alpha Vantage API calls per day (free tier limit)
REDIS_MAX_CONNECTIONS = 20
REDIS_QUEUE_LOCK_TIMEOUT = 10  # seconds
REDIS_CACHE_LOCK_TIMEOUT = 5  # seconds
DEBUG = True