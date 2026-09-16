"""Tests for backend-owned chart range and interval rules."""

from datetime import date

import pytest

from app.services.market_data.chart_config import (
    CHART_RANGES,
    calculate_date_range,
    get_allowed_intervals,
    get_default_interval,
    resolve_interval,
    validate_interval,
)


def test_every_range_has_an_allowed_default():
    for range_key, chart_range in CHART_RANGES.items():
        assert chart_range.default_interval in chart_range.allowed_intervals
        assert get_default_interval(range_key) == chart_range.default_interval


def test_invalid_interval_resolves_to_range_default():
    assert not validate_interval("1y", "5m")
    assert resolve_interval("1y", "5m") == "1d"
    assert get_allowed_intervals("5d") == ["5m", "15m", "30m", "1h"]


def test_range_dates_are_separate_from_interval():
    start, end = calculate_date_range("1y", date(2026, 1, 1))
    assert end == date(2026, 1, 1)
    assert (end - start).days == 365
    assert calculate_date_range("max", date(2026, 1, 1))[0] is None


@pytest.mark.parametrize("range_key", CHART_RANGES)
def test_unknown_interval_never_passes_validation(range_key):
    assert not validate_interval(range_key, "not-an-interval")