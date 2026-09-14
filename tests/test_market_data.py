"""Unit tests for canonical symbols, graph normalization, and fallback order."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.market_data.graph import candle_points, line_points
from app.services.market_data.models import Candle, Instrument, ProviderFailure, Quote
from app.services.market_data.normalization import load_instrument_registry, resolve_instrument, tradingview_chart_symbol
from app.services.market_data.orchestrator import MarketDataOrchestrator


def test_provider_symbol_mapping_preserves_exchange_identity():
    registry = load_instrument_registry()
    brk = registry["BRK-B"]
    assert brk.symbol == "BRK-B"
    assert brk.provider_symbol("tradingview") == "BRK.B"
    assert brk.provider_symbol("yfinance") == "BRK-B"
    assert resolve_instrument("NASDAQ:AAPL", registry).symbol == "AAPL"
    assert tradingview_chart_symbol(registry["AAPL"]) == "NASDAQ:AAPL"


def test_graph_reducer_supports_line_and_candle_points():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [Candle(start + timedelta(days=index), 1, 3, 0, 2, 10) for index in range(600)]
    assert len(line_points(candles)) <= 500
    assert len(candle_points(candles)) <= 500
    assert line_points(candles)[0]["value"] == 2
    assert candle_points(candles)[0]["high"] == 3


class FakeProvider:
    def __init__(self, name: str, candles):
        self.name = name
        self.candles = candles
        self.calls = 0

    async def historical_candles(self, instrument, start, end, interval):
        self.calls += 1
        return self.candles

    async def quote(self, instrument):
        return ProviderFailure(self.name, "quote", "not used")


class FailingProvider(FakeProvider):
    async def historical_candles(self, instrument, start, end, interval):
        self.calls += 1
        return ProviderFailure(self.name, "historical", "temporarily down", retryable=True)


@pytest.mark.asyncio
async def test_historical_fallback_uses_next_provider_after_failure():
    first = FakeProvider("first", ProviderFailure("first", "historical", "down", retryable=False))
    second = FakeProvider("second", [Candle(datetime.now(timezone.utc), 1, 2, 0, 1.5)])
    result = await MarketDataOrchestrator([first, second]).historical_candles(
        Instrument("AAPL"), date(2026, 1, 1), date(2026, 1, 2), "1d"
    )
    assert isinstance(result, list)
    assert result[0].close == 1.5
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_retryable_provider_opens_local_circuit():
    provider = FailingProvider("unavailable", [])
    orchestrator = MarketDataOrchestrator([provider])
    result = await orchestrator.historical_candles(
        Instrument("AAPL"), date(2026, 1, 1), date(2026, 1, 2), "1d"
    )
    assert isinstance(result, ProviderFailure)
    assert provider.calls == 6
    second_result = await orchestrator.historical_candles(
        Instrument("AAPL"), date(2026, 1, 1), date(2026, 1, 2), "1d"
    )
    assert isinstance(second_result, ProviderFailure)
    assert provider.calls == 6
