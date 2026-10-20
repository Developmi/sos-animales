import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from app.shared.geo import geocode_address


@pytest_asyncio.fixture(autouse=True)
async def _init_valkey_for_geo_tests() -> AsyncGenerator[None, None]:
    """Initialize and teardown Valkey client for geo tests."""
    from app.shared.geo import init_valkey, close_valkey
    from app.config import settings

    init_valkey(settings.VALKEY_URL)
    yield
    await close_valkey()


@pytest.mark.asyncio
async def test_geocode_real_address() -> None:
    """Validate that Nominatim returns valid coordinates for a known landmark in Bogota."""
    # Plaza de Bolívar / Alcaldía Mayor in Bogota
    lat, lng = await geocode_address("Plaza de Bolivar", "Bogota")

    assert lat is not None
    assert lng is not None
    # Validate coordinates fall within expected bounding box of Bogota
    assert 4.5 < lat < 4.7
    assert -74.2 < lng < -74.0


@pytest.mark.asyncio
async def test_geocode_fake_address() -> None:
    """Validate that a non-existent address returns None."""
    lat, lng = await geocode_address(
        "Calle Inventada de Mentiras 9999", "MunicipioFalso"
    )

    assert lat is None
    assert lng is None
