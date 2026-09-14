"""Async search, deduplication, and malformed-provider response tests."""

import pytest

from app.services import search
from app.services.market_data.models import Instrument


class FakeRedis:
    def __init__(self):
        self.cached = {"AAPL": "Apple"}

    async def get_user_weights(self, user_id):
        return {}

    async def get_global_weights(self):
        return {}

    async def get_trending_scores(self):
        return {}

    async def get_cached_names(self):
        return self.cached

    async def get_cached_name(self, symbol):
        return self.cached.get(symbol.upper())

    async def get_global_weight(self, symbol):
        return 0.0

    async def get_trending_score(self, symbol):
        return 0.0

    async def reserve_provider_quota(self, provider, period, limit, ttl):
        return True


@pytest.mark.asyncio
async def test_async_search_returns_local_results(monkeypatch):
    registry = {"AAPL": Instrument("AAPL", exchange="US", display_name="Apple")}
    monkeypatch.setattr(search, "load_instrument_registry", lambda: registry)
    monkeypatch.setattr(search, "load_brand_map", lambda: {"AAPL": ["Apple"]})
    monkeypatch.setattr(search, "fetch_symbol_matches", lambda query, redis: _empty_matches())

    results = await search.search_symbols("apple", FakeRedis())

    assert results[0]["symbol"] == "AAPL"
    assert results[0]["instrument_id"] == "STOCK:US:AAPL"
    assert "score" not in results[0]


async def _empty_matches():
    return []


@pytest.mark.asyncio
async def test_external_search_skips_malformed_and_deduplicates(monkeypatch):
    registry = {"AAPL": Instrument("AAPL", exchange="US")}
    monkeypatch.setattr(search, "load_instrument_registry", lambda: registry)
    monkeypatch.setattr(search, "load_brand_map", lambda: {})

    async def fake_matches(query, redis):
        return [
            {},
            {"1. symbol": "AAPL", "2. name": "Apple Inc."},
            {"1. symbol": "AAPL", "2. name": "Apple Inc."},
        ]

    monkeypatch.setattr(search, "fetch_symbol_matches", fake_matches)
    seen = set()
    results = await search.search_external_symbols("apple", FakeRedis(), {}, seen, registry)

    assert len(results) == 1
    assert len(seen) == 1
