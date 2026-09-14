"""Graph-friendly normalization for candle and line chart responses."""

from collections.abc import Sequence
from dataclasses import asdict

from app.services.market_data.models import Candle


def normalize_candles(candles: Sequence[Candle], max_points: int = 500) -> list[Candle]:
    """Reduce dense candles into stable OHLCV buckets while preserving extremes.

    This is a deterministic min/max bucket reducer rather than an invented price
    value: open and close remain the bucket boundaries, while high/low preserve
    the visible range and volume is summed.
    """
    if len(candles) <= max_points:
        return list(candles)
    bucket_size = max(1, len(candles) // max_points)
    reduced: list[Candle] = []
    for offset in range(0, len(candles), bucket_size):
        bucket = list(candles[offset:offset + bucket_size])
        valid = [item for item in bucket if item.close is not None]
        if not valid:
            continue
        reduced.append(Candle(
            timestamp=valid[0].timestamp,
            open=valid[0].open,
            high=max((item.high for item in valid if item.high is not None), default=None),
            low=min((item.low for item in valid if item.low is not None), default=None),
            close=valid[-1].close,
            volume=sum(item.volume or 0 for item in valid),
            vwap=None,
        ))
    return reduced[:max_points]


def line_points(candles: Sequence[Candle], max_points: int = 500) -> list[dict]:
    """Return timestamp/close points for a line graph."""
    return [
        {"time": candle.timestamp.isoformat(), "value": candle.close}
        for candle in normalize_candles(candles, max_points)
        if candle.close is not None
    ]


def candle_points(candles: Sequence[Candle], max_points: int = 500) -> list[dict]:
    """Return normalized OHLCV points for a candlestick graph."""
    return [
        {
            "time": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in normalize_candles(candles, max_points)
    ]
