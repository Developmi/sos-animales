"""Tests for Valkey lifecycle management in geo.py.

Tests init_valkey, close_valkey, and that geocode_address works
after lifecycle initialization instead of import-time connection.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.shared import geo
from app.shared.geo import close_valkey, geocode_address, init_valkey


def test_init_valkey_creates_client() -> None:
    """init_valkey should create a Redis client and return it."""
    client = init_valkey(settings.VALKEY_URL)
    assert client is not None
    assert geo.valkey_client is not None
    assert geo.valkey_client is client


@pytest.mark.asyncio
async def test_init_valkey_client_can_ping() -> None:
    """After init_valkey, the client should be usable for PING."""
    init_valkey(settings.VALKEY_URL)
    assert geo.valkey_client is not None
    result = await geo.valkey_client.ping()
    assert result is True


@pytest.mark.asyncio
async def test_close_valkey_sets_none() -> None:
    """close_valkey should close the client and set it to None."""
    init_valkey(settings.VALKEY_URL)
    await close_valkey()
    assert geo.valkey_client is None


@pytest.mark.asyncio
async def test_geocode_address_after_init_valkey() -> None:
    """geocode_address should work when valkey_client is set via init_valkey."""
    client = init_valkey(settings.VALKEY_URL)
    await client.delete("geo:plaza de bolivar, bogota, colombia")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"lat": "4.5981", "lon": "-74.0758"}]

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_http
    mock_cm.__aexit__.return_value = False

    with patch("app.shared.geo.httpx.AsyncClient", return_value=mock_cm):
        lat, lng = await geocode_address("Plaza de Bolivar", "Bogota")

    assert lat is not None
    assert lng is not None
    assert 4.5 < lat < 4.7
    assert -74.2 < lng < -74.0
