"""Tests for Valkey lifecycle management in geo.py.

Tests init_valkey, close_valkey, and that geocode_address works
after lifecycle initialization instead of import-time connection.
"""

import pytest
from app.shared import geo
from app.shared.geo import init_valkey, close_valkey, geocode_address
from app.config import settings


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
    init_valkey(settings.VALKEY_URL)
    lat, lng = await geocode_address("Plaza de Bolivar", "Bogota")
    assert lat is not None
    assert lng is not None
    assert 4.5 < lat < 4.7
    assert -74.2 < lng < -74.0
