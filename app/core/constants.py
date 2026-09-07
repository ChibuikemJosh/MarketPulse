# Core constants for the MarketPulse application

ANONYMOUS_USER_ID = None

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

CLICK_BATCH_SIZE = 10
CLICK_LOOKBACK_DAYS = 30
CLICK_DECAY_FACTOR = 0.8

FUZZ_THRESHOLD = 50
FINAL_THRESHOLD = 70

TRENDING_SCORE_SCALE = 100
ALPHAVANTAGE_DEFAULT_SCORE = 50

REFRESH_SECONDS = 600

JUNK_SUFFIXES = (
    " Corporation", " Corp", " Inc.", " Inc", " Ltd.", " Ltd", " Limited",
    " Plc", " Group", " Holdings", " Common Stock", " Class A", " Class B",
    " ADR", " Co ", " Co.",
)