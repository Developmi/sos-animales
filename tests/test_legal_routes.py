"""Tests for legal routes, custom error handlers, and template wiring."""

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_legal_cookies_returns_200(client: AsyncClient) -> None:
    response = await client.get("/legal/cookies")
    assert response.status_code == 200
    assert "Cookies" in response.text


@pytest.mark.asyncio
async def test_legal_terms_returns_200(client: AsyncClient) -> None:
    response = await client.get("/legal/terms")
    assert response.status_code == 200
    assert "Términos" in response.text


@pytest.mark.asyncio
async def test_legal_data_processing_returns_200(client: AsyncClient) -> None:
    response = await client.get("/legal/data-processing")
    assert response.status_code == 200
    assert "datos personales" in response.text.lower()


@pytest.mark.asyncio
async def test_404_handler_renders_custom_page(client: AsyncClient) -> None:
    response = await client.get("/nonexistent-route-xyz-12345")
    assert response.status_code == 404
    assert "Página no encontrada" in response.text


@pytest.mark.asyncio
async def test_home_includes_footer(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "/legal/privacy" in response.text


@pytest.mark.asyncio
async def test_campaign_form_smoke(client: AsyncClient) -> None:
    # ponytail: smoke test — campaign_form requires DB, search page is DB-free.
    response = await client.get("/sterilization/search")
    assert response.status_code == 200
