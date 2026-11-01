"""Tests for static assets and favicon serving."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_favicon_endpoint_returns_ico() -> None:
    """GET /favicon.ico must serve the official favicon with status 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/favicon.ico")
    assert response.status_code == 200
    assert (
        "image" in response.headers.get("content-type", "")
        or response.headers.get("content-type") == "image/vnd.microsoft.icon"
    )
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_offline_vendor_assets_exist_and_accessible() -> None:
    """Verify vendored HTMX and Leaflet assets are served correctly via /static."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # HTMX
        htmx_res = await client.get("/static/js/vendor/htmx.min.js")
        assert htmx_res.status_code == 200
        assert "htmx" in htmx_res.text

        # Leaflet JS
        leaflet_js_res = await client.get("/static/js/vendor/leaflet.js")
        assert leaflet_js_res.status_code == 200
        assert "Leaflet" in leaflet_js_res.text

        # Leaflet CSS
        leaflet_css_res = await client.get("/static/css/vendor/leaflet.css")
        assert leaflet_css_res.status_code == 200
        assert "leaflet" in leaflet_css_res.text

        # Leaflet Marker Image
        marker_res = await client.get("/static/images/vendor/leaflet/marker-icon.png")
        assert marker_res.status_code == 200
        assert len(marker_res.content) > 0


def test_no_external_cdn_in_templates() -> None:
    """Verify that templates do not reference unpkg or jsdelivr for libraries."""
    template_files = list(Path("app").rglob("*.html"))
    for tf in template_files:
        content = tf.read_text(encoding="utf-8")
        assert "unpkg.com/leaflet" not in content, f"External Leaflet CDN found in {tf}"
        assert "cdn.jsdelivr.net/npm/htmx" not in content, (
            f"External HTMX CDN found in {tf}"
        )
        assert "cdn.jsdelivr.net/npm/@picocss" not in content, (
            f"External Pico CSS CDN found in {tf}"
        )
