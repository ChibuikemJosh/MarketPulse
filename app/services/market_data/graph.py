"""Semantic candle formatting and visual line simplification.

Candlestick data is never reduced by point count. A candle remains the interval
returned by the provider. Line charts may remove visually redundant close
points because that changes only the visualization, not market data.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.services.market_data.models import Candle

LINE_MAX_POINTS = 500
LINE_SLOPE_RELATIVE_TOLERANCE = 0.02
LINE_DEVIATION_RELATIVE_TOLERANCE = 0.001
_VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"}
_INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 1440, "1wk": 10080}


def _timestamp(value: datetime) -> float:
    """Convert timestamps to UTC seconds for stable slope calculations."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).timestamp()


def _valid_candles(candles: Sequence[Candle]) -> list[Candle]:
    """Keep valid close-bearing candles in chronological order."""
    return sorted((candle for candle in candles if candle.close is not None), key=lambda candle: _timestamp(candle.timestamp))


def candle_points(candles: Sequence[Candle]) -> list[dict[str, Any]]:
    """Convert actual candles to frontend OHLCV points without changing them."""
    return [
        {"time": candle.timestamp.isoformat(), "open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close, "volume": candle.volume, "vwap": candle.vwap}
        for candle in candles
    ]


def prepare_line_points(candles: Sequence[Candle]) -> list[dict[str, Any]]:
    """Extract close values while retaining the selected candle timestamps."""
    return [{"time": candle.timestamp.isoformat(), "value": candle.close} for candle in _valid_candles(candles)]


def _point_time(point: dict[str, Any]) -> float:
    """Parse an ISO point timestamp or accept a numeric timestamp."""
    value = point["time"]
    if isinstance(value, (int, float)):
        return float(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _timestamp(parsed)


def _slope(first: dict[str, Any], second: dict[str, Any]) -> float:
    """Calculate price change per second, accounting for irregular timestamps."""
    elapsed = _point_time(second) - _point_time(first)
    return (float(second["value"]) - float(first["value"])) / elapsed if elapsed > 0 else 0.0


def _deviation(first: dict[str, Any], middle: dict[str, Any], last: dict[str, Any]) -> float:
    """Return normalized distance from the timestamp-weighted first-to-last line."""
    first_time, middle_time, last_time = _point_time(first), _point_time(middle), _point_time(last)
    span = last_time - first_time
    if span <= 0:
        return float("inf")
    ratio = (middle_time - first_time) / span
    expected = float(first["value"]) + (float(last["value"]) - float(first["value"])) * ratio
    scale = max(abs(float(first["value"])), abs(float(middle["value"])), abs(float(last["value"])), 1.0)
    return abs(float(middle["value"]) - expected) / scale


def _redundant(first: dict[str, Any], middle: dict[str, Any], last: dict[str, Any], slope_tolerance: float, deviation_tolerance: float) -> bool:
    """Determine whether a middle point is visually redundant."""
    slope_before, slope_after = _slope(first, middle), _slope(middle, last)
    direction_change = (slope_before > 0) != (slope_after > 0) if slope_before and slope_after else slope_before != slope_after
    if direction_change:
        return False
    slope_scale = max(abs(_slope(first, last)), abs(slope_before), abs(slope_after), 1e-12)
    slope_difference = abs(slope_before - slope_after) / slope_scale
    return slope_difference <= slope_tolerance and _deviation(first, middle, last) <= deviation_tolerance


def _is_valid_point(point: dict[str, Any]) -> bool:
    """Check that a line point has finite time and close value."""
    try:
        return isfinite(_point_time(point)) and isfinite(float(point["value"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def simplify_line(points: Sequence[dict[str, Any]], max_points: int = LINE_MAX_POINTS, slope_tolerance: float = LINE_SLOPE_RELATIVE_TOLERANCE, deviation_tolerance: float = LINE_DEVIATION_RELATIVE_TOLERANCE) -> list[dict[str, Any]]:
    """Remove near-collinear points while preserving extrema and endpoints.

    Each A-B-C decision uses slopes per second and the normalized distance of B
    from the timestamp-aware A-to-C line. If a large dataset remains, the same
    geometric test is repeated with gradually relaxed named tolerances; no
    fixed-stride sampling or price averaging is used.
    """
    if len(points) <= 2:
        return list(points)
    result = [dict(point) for point in points if _is_valid_point(point)]
    if len(result) <= 2:
        return result
    current_slope, current_deviation = slope_tolerance, deviation_tolerance
    while True:
        changed = True
        while changed and len(result) > 2:
            changed = False
            kept = [result[0]]
            for index in range(1, len(result) - 1):
                if _redundant(result[index - 1], result[index], result[index + 1], current_slope, current_deviation):
                    changed = True
                else:
                    kept.append(result[index])
            kept.append(result[-1])
            result = kept
        if len(result) <= max_points or current_slope >= 1.0:
            return result
        current_slope *= 2
        current_deviation *= 2


def line_points(candles: Sequence[Candle], max_points: int = LINE_MAX_POINTS) -> list[dict[str, Any]]:
    """Return simplified close points for a line chart."""
    return simplify_line(prepare_line_points(candles), max_points=max_points)


def aggregate_candles(candles: Sequence[Candle], source_interval: str, target_interval: str) -> list[Candle]:
    """Aggregate only compatible intervals using standard OHLCV semantics."""
    if source_interval not in _VALID_INTERVALS or target_interval not in _VALID_INTERVALS:
        raise ValueError("Unsupported candle interval")
    if source_interval == target_interval:
        return list(candles)
    if target_interval == "1mo" and source_interval == "1wk":
        key = lambda candle: (candle.timestamp.year, candle.timestamp.month)
    elif target_interval == "1wk" and source_interval == "1d":
        key = lambda candle: candle.timestamp.isocalendar()[:2]
    else:
        source_minutes, target_minutes = _INTERVAL_MINUTES.get(source_interval), _INTERVAL_MINUTES.get(target_interval)
        if source_minutes is None or target_minutes is None or target_minutes <= source_minutes or target_minutes % source_minutes:
            raise ValueError(f"Cannot aggregate {source_interval} to {target_interval}")
        key = lambda candle: int(_timestamp(candle.timestamp) // (target_minutes * 60))
    buckets: dict[Any, list[Candle]] = {}
    for candle in sorted(candles, key=lambda item: _timestamp(item.timestamp)):
        buckets.setdefault(key(candle), []).append(candle)
    aggregated: list[Candle] = []
    for bucket in buckets.values():
        valid = [item for item in bucket if item.close is not None]
        if not valid:
            continue
        aggregated.append(Candle(
            timestamp=valid[0].timestamp,
            open=valid[0].open,
            high=max((item.high for item in valid if item.high is not None), default=None),
            low=min((item.low for item in valid if item.low is not None), default=None),
            close=valid[-1].close,
            volume=sum((item.volume or 0) for item in valid) if any(item.volume is not None for item in valid) else None,
            vwap=None,
        ))
    return aggregated
