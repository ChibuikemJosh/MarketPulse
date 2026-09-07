"""Value object for a user's saved stock."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WatchlistItem:
    """A stock saved to one authenticated user's watchlist."""

    user_id: int
    symbol: str
    created_at: datetime | None = None
