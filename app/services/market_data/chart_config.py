"""Backend-owned chart range and candle-interval rules.

The range controls how much history is requested. The interval controls what
one returned candle represents. These rules intentionally reflect the current
provider set: yfinance is the primary historical source, Massive is optional,
and Tiingo is daily-or-coarser only.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class ChartRange:
    """Configuration for one supported chart range."""

    key: str
    default_interval: str
    allowed_intervals: tuple[str, ...]
    days: int | None


CHART_RANGES: dict[str, ChartRange] = {
    "1d": ChartRange("1d", "5m", ("1m", "5m", "15m", "30m", "1h"), 1),
    "5d": ChartRange("5d", "15m", ("5m", "15m", "30m", "1h"), 5),
    "1mo": ChartRange("1mo", "1h", ("15m", "30m", "1h", "1d"), 30),
    "3mo": ChartRange("3mo", "1d", ("1h", "1d"), 90),
    "6mo": ChartRange("6mo", "1d", ("1d",), 180),
    "1y": ChartRange("1y", "1d", ("1d", "1wk"), 365),
    "5y": ChartRange("5y", "1wk", ("1d", "1wk", "1mo"), 1825),
    "max": ChartRange("max", "1mo", ("1wk", "1mo"), None),
}


def get_chart_range(range_key: str | None) -> ChartRange:
    """Return a configured range or the one-year default."""
    return CHART_RANGES.get((range_key or "1y").lower(), CHART_RANGES["1y"])


def get_default_interval(range_key: str | None) -> str:
    """Return the default interval for a range."""
    return get_chart_range(range_key).default_interval


def get_allowed_intervals(range_key: str | None) -> list[str]:
    """Return intervals supported by the selected range."""
    return list(get_chart_range(range_key).allowed_intervals)


def validate_interval(range_key: str | None, interval: str | None) -> bool:
    """Return whether an interval is explicitly allowed for a range."""
    return bool(interval) and interval in get_chart_range(range_key).allowed_intervals


def resolve_interval(range_key: str | None, interval: str | None) -> str:
    """Resolve a missing or invalid interval to the range's documented default."""
    chart_range = get_chart_range(range_key)
    return interval if interval in chart_range.allowed_intervals else chart_range.default_interval


def calculate_date_range(range_key: str | None, end_date: date | None = None) -> tuple[date | None, date]:
    """Calculate request dates without changing the selected candle interval.

    ``max`` returns ``None`` as its start date so providers can request their
    available history. Other ranges use calendar days; providers still decide
    which trading sessions actually contain candles.
    """
    end = end_date or date.today()
    days = get_chart_range(range_key).days
    return (end - timedelta(days=days) if days is not None else None, end)
