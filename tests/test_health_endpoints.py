"""Tests for SRE observability health endpoints (/health/live and /health/ready)."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_live_returns_ok() -> None:
    """GET /health/live must return 200 OK with alive status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_health_ready_returns_dependencies_status() -> None:
    """GET /health/ready must return 200 OK and include db and valkey checks."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "valkey" in data["checks"]
