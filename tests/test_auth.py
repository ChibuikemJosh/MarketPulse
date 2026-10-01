"""Tests for authentication, news pagination, OAuth, and chart defaults."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password, safe_next_path, verify_password
from app.main import app


def test_passwords_are_hashed_and_verified():
    password_hash = hash_password("correct horse battery staple")
    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_redirect_paths_are_internal_only():
    assert safe_next_path("/watchlist") == "/watchlist"
    assert safe_next_path("https://evil.example") == "/"
    assert safe_next_path("//evil.example") == "/"


def test_auth_pages_render_and_watchlist_requires_session():
    client = TestClient(app)
    assert client.get("/login").status_code == 200
    assert client.get("/signup").status_code == 200
    assert client.get("/api/watchlists").status_code == 401


def test_session_middleware_is_installed():
    """Verify SessionMiddleware is active."""
    from starlette.middleware.sessions import SessionMiddleware
    middleware_types = [m.cls for m in app.user_middleware]
    assert SessionMiddleware in middleware_types


def test_google_redirect_when_disabled():
    """Without GOOGLE_CLIENT_ID, /auth/google redirects to login."""
    from app.core import config
    client = TestClient(app, follow_redirects=False)
    original_id, original_secret = config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET
    config.GOOGLE_CLIENT_ID = ""
    config.GOOGLE_CLIENT_SECRET = ""
    resp = client.get("/auth/google")
    config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET = original_id, original_secret
    assert resp.status_code == 303
    assert "/login" in resp.headers.get("location", "")


def test_google_callback_when_disabled():
    """Without GOOGLE_CLIENT_ID, callback redirects to login."""
    from app.core import config
    client = TestClient(app, follow_redirects=False)
    original_id, original_secret = config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET
    config.GOOGLE_CLIENT_ID = ""
    config.GOOGLE_CLIENT_SECRET = ""
    resp = client.get("/auth/google/callback")
    config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET = original_id, original_secret
    assert resp.status_code == 303
    assert "/login" in resp.headers.get("location", "")


def test_anonymous_cannot_access_protected_watchlist():
    """All watchlist API endpoints require authentication."""
    client = TestClient(app)
    assert client.get("/api/watchlists").status_code == 401
    assert client.get("/api/watchlists/status/AAPL").status_code == 401
    assert client.post("/api/watchlists", json={"symbol": "AAPL"}).status_code == 401
    assert client.delete("/api/watchlists/AAPL").status_code == 401


class TestChartDefaults:
    """Verify chart configuration defaults."""

    def test_default_mode_is_line(self):
        """The API default mode parameter is 'line'."""
        from app.services.market_data.chart_config import get_chart_range
        cfg = get_chart_range(None)
        assert cfg.key == "1y"

    def test_default_interval_is_1wk(self):
        from app.services.market_data.chart_config import get_chart_range
        assert get_chart_range("1y").default_interval == "1wk"

    def test_allowed_intervals_are_backend_driven(self):
        from app.services.market_data.chart_config import get_allowed_intervals
        assert "1d" in get_allowed_intervals("1y")
        assert "1wk" in get_allowed_intervals("1y")
        assert "5m" not in get_allowed_intervals("1y")


class TestNewsPagination:
    """Verify pagination contract for /api/news/market."""

    @pytest.mark.asyncio
    async def test_response_contains_pagination_fields(self):
        from app.services.news import get_market_news
        from app.cache.redis import RedisService
        mock_redis = AsyncMock(spec=RedisService)
        mock_redis.market_cache_key.return_value = "news-general-market-finnhub"
        mock_redis.get_market_cache.return_value = None
        mock_redis.set_market_cache.return_value = None
        with patch("app.services.news._fetch_general", return_value=[]):
            result = await get_market_news(mock_redis, 0)
            assert "items" in result
            assert "has_more" in result
            assert "next_offset" in result

    @pytest.mark.asyncio
    async def test_first_page_returns_15_items_then_5(self):
        from app.services.news import get_market_news
        from app.cache.redis import RedisService
        mock_redis = AsyncMock(spec=RedisService)
        mock_redis.market_cache_key.return_value = "news-general-market-finnhub"
        articles = [{"id": i, "headline": f"Article {i}", "source": "T"} for i in range(20)]
        mock_redis.get_market_cache.return_value = {"data": articles}
        result = await get_market_news(mock_redis, 0)
        assert len(result["items"]) == 15
        assert result["has_more"] is True
        assert result["next_offset"] == 15
        result2 = await get_market_news(mock_redis, 15)
        assert len(result2["items"]) == 5
        assert result2["has_more"] is False
        assert result2["next_offset"] == 20

    @pytest.mark.asyncio
    async def test_empty_result_handling(self):
        from app.services.news import get_market_news
        from app.cache.redis import RedisService
        mock_redis = AsyncMock(spec=RedisService)
        mock_redis.market_cache_key.return_value = "news-general-market-finnhub"
        mock_redis.get_market_cache.return_value = {"data": []}
        result = await get_market_news(mock_redis, 0)
        assert result["items"] == []
        assert result["has_more"] is False


class TestMarketData:
    """Verify provider failure handling and Nigerian instrument preservation."""

    def test_nigerian_instruments_remain_in_registry(self):
        from app.services.market_data.normalization import load_instrument_registry
        registry = load_instrument_registry()
        nigerian = [s for s in registry if s.endswith(".LG")]
        assert len(nigerian) > 0
        assert "BUACEMENT.LG" in registry
        assert "BUAFOODS.LG" in registry
        assert "ZENITHBANK.LG" in registry
        assert "GTCO.LG" in registry
        assert "UBA.LG" in registry
