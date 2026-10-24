"""Tests for legal routes, custom error handlers, and template wiring."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
    # Verify cookie consent banner is included with links to policies and Plausible blocker script
    assert "cookie-consent" in response.text
    assert "/legal/cookies" in response.text
    assert "/legal/data-processing" in response.text
    assert "plausible-tracker-script" in response.text


@pytest.mark.asyncio
async def test_plausible_meta_rendered_when_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "PLAUSIBLE_DOMAIN", "sos-animales.test")
    monkeypatch.setattr(settings, "PLAUSIBLE_URL", "https://plausible.test/script.js")

    response = await client.get("/")
    assert response.status_code == 200
    assert '<meta name="plausible-domain" content="sos-animales.test"' in response.text
    assert (
        '<meta name="plausible-url" content="https://plausible.test/script.js"'
        in response.text
    )


@pytest.mark.asyncio
async def test_campaign_form_smoke(client: AsyncClient) -> None:
    # ponytail: smoke test — campaign_form requires DB, search page is DB-free.
    response = await client.get("/sterilization/search")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_validation_error_handler_returns_422_html(client: AsyncClient) -> None:
    response = await client.post(
        "/animals/1/adopt",
        data={"pin": "invalid-pin-too-long"},
        headers={"accept": "text/html"},
    )
    assert response.status_code == 422
    assert "Datos inválidos" in response.text


@pytest.mark.asyncio
async def test_validation_error_handler_returns_422_json(client: AsyncClient) -> None:
    response = await client.post(
        "/animals/1/adopt",
        data={"pin": "invalid-pin-too-long"},
        headers={"accept": "application/json"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
