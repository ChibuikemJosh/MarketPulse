# Cache keys for the MarketPulse application

USER_WEIGHTS = "cache:user:{user_id}:weights"
GLOBAL_WEIGHTS = "cache:global:weights"
TRENDING = "cache:trending_scores"
TRENDING_METADATA = "cache:trending_metadata"
CACHED_NAMES = "cache:cached_names"

CLICK_QUEUE_LOCK = "lock:queue:clicks"
CLICK_CACHE_LOCK = "lock:cache:clicks"
GLOBAL_CACHE_LOCK = "lock:cache:global"

API_STATS = "api:stats:alpha_vantage:calls:{today_str}"

CLICK_QUEUE = "queue:clicks"

MARKET_CACHE = "market:{operation}:{instrument_id}:{provider}:{interval}:{start}:{end}"
MARKET_FAILURE = "market:failure:{operation}:{instrument_id}:{provider}:{interval}:{start}:{end}"
PROVIDER_CIRCUIT = "provider:circuit:{provider}:{operation}"
PROVIDER_QUOTA = "provider:quota:{provider}:{period}"
REFRESH_LEADER_LOCK = "lock:market:refresh"