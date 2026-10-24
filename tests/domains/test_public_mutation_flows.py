"""Integration tests for critical public mutation flows:
- Public shelter self-registration (/sources/register)
- Public rescuer PIN-based adoption (/animals/{id}/adopt)
- Public animal profile creation and background PIN email dispatch to source.contact_email
"""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.animals.models import AnimalProfile
from app.domains.animals.tools import create_animal_profile
from app.domains.sources.models import Source
from app.main import app


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client bound to the test database session."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_test_source(db_session: AsyncSession) -> Source:
    source = Source(
        name="Refugio San Roque",
        type="verified_shelter",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="sanroque@sos-animales.org",
        contact_whatsapp="+573101234567",
        is_active=True,
        status="verified",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def sample_animal_with_pin(
    db_session: AsyncSession, sample_test_source: Source
) -> tuple[AnimalProfile, str]:
    """Create an animal and return the instance along with the raw plaintext PIN."""
    data = {
        "name": "Canela",
        "species": "canino",
        "municipality": "Bogotá",
        "breed": "Criolla",
        "age_years": 2,
    }
    result = await create_animal_profile(
        db_session, sample_test_source.id, data, "https://ejemplo.com/canela.jpg"
    )
    return result["animal"], result["raw_pin"]


# ── TEST 1: Public shelter self-registration ─────────────────────────────────


@pytest.mark.asyncio
async def test_public_source_registration_success(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A public shelter must be able to self-register without an admin session."""
    form_data = {
        "name": "Fundación Patitas Felices",
        "type": "verified_shelter",
        "department": "Antioquia",
        "municipality": "Medellín",
        "contact_email": "contacto@patitasfelices.org",
        "contact_whatsapp": "+573001234567",
        "contact_url": "https://instagram.com/patitasfelices",
        "accept_terms": "true",
    }

    response = await app_client.post(
        "/sources/register", data=form_data, follow_redirects=False
    )

    # Must be 200 OK with confirmation message, NEVER 302 to /auth/login
    assert response.status_code == 200
    assert (
        "solicitud enviada" in response.text.lower()
        or "gracias por registrar" in response.text.lower()
    )


# ── TEST 2: Public rescuer adoption via PIN ──────────────────────────────────


@pytest.mark.asyncio
async def test_public_rescuer_can_adopt_with_valid_pin(
    app_client: AsyncClient,
    sample_animal_with_pin: tuple[AnimalProfile, str],
    db_session: AsyncSession,
) -> None:
    """Rescuer who holds the PIN must be able to mark animal as adopted without admin rights."""
    animal, raw_pin = sample_animal_with_pin

    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": raw_pin},
        follow_redirects=False,
    )

    # Must be 200 OK with confirmation, NEVER 302 to /auth/login
    assert response.status_code == 200
    assert "adoptado" in response.text.lower()

    # Verify state change in database
    await db_session.refresh(animal)
    assert animal.status == "adopted"
    assert animal.adopted_at is not None


@pytest.mark.asyncio
async def test_public_rescuer_adopt_with_invalid_pin_rejected(
    app_client: AsyncClient,
    sample_animal_with_pin: tuple[AnimalProfile, str],
    db_session: AsyncSession,
) -> None:
    """An incorrect PIN does not change adoption status and renders an error message."""
    animal, _ = sample_animal_with_pin

    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": "9999"},  # Invalid PIN
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "incorrecto" in response.text.lower() or "error" in response.text.lower()

    await db_session.refresh(animal)
    assert animal.status == "available"


# ── TEST 3: Animal creation and contact_email resolution ─────────────────────


@pytest.mark.asyncio
async def test_post_animal_reads_source_contact_email(
    app_client: AsyncClient,
    sample_test_source: Source,
    db_session: AsyncSession,
) -> None:
    """Publishing an animal must not fail with AttributeError: source.email."""
    with patch("app.domains.animals.router.send_pin_email_sync") as mock_email:
        data = {
            "source_id": str(sample_test_source.id),
            "name": "Boby",
            "species": "canino",
            "municipality": "Bogotá",
            "breed": "Criollo",
            "age_years": "3",
            "size": "mediano",
        }
        files = {"foto": ("boby.jpg", b"fake-image-bytes", "image/jpeg")}

        response = await app_client.post(
            "/animals/",
            data=data,
            files=files,
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert (
            "perfil creado" in response.text.lower()
            or "publicado" in response.text.lower()
        )
        # Verify that outgoing email used source.contact_email
        mock_email.assert_called_once()
        args, _ = mock_email.call_args
        assert args[0] == "sanroque@sos-animales.org"
        assert args[1] == "Boby"
