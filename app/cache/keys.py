# Cache keys for the MarketPulse application

USER_WEIGHTS = "cache:user:{user_id}:weights"
GLOBAL_WEIGHTS = "cache:global:weights"
TRENDING = "cache:trending_scores"
CACHED_NAMES = "cache:cached_names"

CLICK_QUEUE_LOCK = "lock:queue:clicks"
CLICK_CACHE_LOCK = "lock:cache:clicks"
GLOBAL_CACHE_LOCK = "lock:cache:global"

API_STATS = "api:stats:alpha_vantage:calls:{today_str}"

CLICK_QUEUE = "queue:clicks"