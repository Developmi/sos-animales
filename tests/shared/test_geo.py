from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.shared.geo import geocode_address


@pytest_asyncio.fixture(autouse=True)
async def _init_valkey_for_geo_tests() -> AsyncGenerator[None, None]:
    """Initialize and teardown Valkey client for geo tests."""
    from app.config import settings
    from app.shared.geo import close_valkey, init_valkey

    client = init_valkey(settings.VALKEY_URL)
    await client.delete(
        "geo:plaza de bolivar, bogota, colombia",
        "geo:calle inventada de mentiras 9999, municipiofalso, colombia",
    )
    yield
    await close_valkey()


@pytest.mark.asyncio
async def test_geocode_real_address() -> None:
    """Validate that Nominatim returns valid coordinates for a known landmark in Bogota."""
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


@pytest.mark.asyncio
async def test_geocode_fake_address() -> None:
    """Validate that a non-existent address returns None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_http
    mock_cm.__aexit__.return_value = False

    with patch("app.shared.geo.httpx.AsyncClient", return_value=mock_cm):
        lat, lng = await geocode_address(
            "Calle Inventada de Mentiras 9999", "MunicipioFalso"
        )

    assert lat is None
    assert lng is None
