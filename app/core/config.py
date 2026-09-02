from dotenv import load_dotenv
from os import getenv

# Core configuration for the MarketPulse application

load_dotenv()

REDIS_URL = getenv("REDIS_URL") or "redis://localhost:6379"

DATABASE_URL = getenv("DATABASE_URL") or "sqlite:///./marketpulse.db"
DB_PATH = DATABASE_URL.replace("sqlite:///", "")  # Extract the file path from the DATABASE_URL

SECRET_KEY = getenv("SECRET_KEY") or ""
ALPHA_VANTAGE_API_KEY = getenv("ALPHA_VANTAGE_API_KEY") or ""
FINNHUB_API_KEY = getenv("FINNHUB_API_KEY") or ""
GEMINI_API_KEY = getenv("GEMINI_API_KEY") or ""

API_LIMITS = {
    "ALPHA_VANTAGE": 25
}  # Max Alpha Vantage API calls per day (free tier limit)

REDIS_MAX_CONNECTIONS = 20
REDIS_QUEUE_LOCK_TIMEOUT = 10  # seconds
REDIS_CACHE_LOCK_TIMEOUT = 5  # seconds

DEBUG = True