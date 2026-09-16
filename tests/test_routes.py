"""Route and template registration checks."""

from app.main import app


def test_fastapi_routes_are_registered():
    paths = set(app.openapi()["paths"])
    assert "/api/search" in paths
    assert "/api/dashboard-updates" in paths
    assert "/api/graph/{instrument_id}" in paths
    assert "/api/chart-config" in paths
    assert "/candles/{instrument_id}" in paths
    assert "/quote" in paths
    assert "/static" in {route.path for route in app.routes if hasattr(route, "path")}


def test_static_urls_use_fastapi_style():
    from pathlib import Path

    for template_name in ("layout.html", "index.html"):
        content = (Path("app/templates") / template_name).read_text(encoding="utf-8")
        assert "url_for('static'" not in content
        assert "/static/" in content
