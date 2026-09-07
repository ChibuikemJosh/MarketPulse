"""Value object describing a stock interaction queued for persistence."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ClickRecord:
    """A stock click produced by an authenticated or anonymous visitor."""

    symbol: str
    user_id: Optional[str]
    timestamp: datetime
