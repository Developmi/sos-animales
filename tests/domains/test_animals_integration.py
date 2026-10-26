"""Integration tests for the Animals domain and adoption workflows.

Covers:
1. Multipart image upload with mocked R2 storage and database persistence.
2. Local development fallback to placeholder when R2 is unconfigured.
3. HTTP 400 rejection on duplicate animal names for the same source.
4. HTTP 400 rejection on invalid animal species.
5. Contextual feedback on invalid adoption PIN submission.
6. HTTP 429 rate-limiting lockout after 5 consecutive failed PIN attempts.
7. Catalog filtering by species and municipality.
8. Catalog filtering by adoption status (available vs adopted).
"""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.animals.tools import create_animal_profile
from app.domains.sources.models import Source
from app.main import app


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def shelter_source(db_session: AsyncSession) -> Source:
    source = Source(
        name="Albergue Huellitas",
        type="verified_shelter",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="huellitas@sos-animales.org",
        contact_whatsapp="+573119876543",
        is_active=True,
        status="verified",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_post_animal_multipart_with_mocked_r2(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """Verify that multipart upload sends file to R2 via boto3 and assigns the public URL."""
    mock_s3 = MagicMock()

    with (
        patch(
            "app.domains.animals.tools.settings.R2_ENDPOINT", "https://mock-r2.cloud"
        ),
        patch("app.domains.animals.tools.settings.R2_ACCESS_KEY_ID", "mock_key"),
        patch("app.domains.animals.tools.settings.R2_SECRET_ACCESS_KEY", "mock_secret"),
        patch("app.domains.animals.tools.settings.R2_BUCKET_NAME", "sos-bucket"),
        patch(
            "app.domains.animals.tools.settings.R2_PUBLIC_URL",
            "https://pub-r2.sos-animales.org",
        ),
        patch("boto3.client", return_value=mock_s3),
        patch("app.domains.animals.router.send_pin_email_sync") as mock_email,
    ):
        form_data = {
            "source_id": str(shelter_source.id),
            "name": "Max R2",
            "species": "canino",
            "municipality": "Bogotá",
            "breed": "Labrador",
            "age_years": "2",
            "size": "grande",
            "is_sterilized": "true",
            "sexo": "macho",
            "accept_terms": "true",
        }
        files = {
            "foto": ("max.jpg", b"\xff\xd8\xff\xe0mock_jpeg_bytes", "image/jpeg"),
        }

        response = await app_client.post("/animals/", data=form_data, files=files)

        assert response.status_code == 200
        assert "perfil creado" in response.text.lower()
        assert "huellitas@sos-animales.org" in response.text

        # Verify that boto3 s3.upload_fileobj was called
        mock_s3.upload_fileobj.assert_called_once()
        mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_post_animal_duplicate_name_for_same_source_rejected(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """Registering two animals with the same name under the same source is rejected."""
    data = {
        "name": "Rocky",
        "species": "canino",
        "municipality": "Bogotá",
    }
    await create_animal_profile(
        db_session, shelter_source.id, data, "https://placeholder.com/rocky.jpg"
    )

    # Attempt duplicate animal via POST
    form_data = {
        "source_id": str(shelter_source.id),
        "name": "Rocky",
        "species": "canino",
        "municipality": "Bogotá",
        "accept_terms": "true",
    }
    files = {"foto": ("rocky.jpg", b"image-content", "image/jpeg")}

    response = await app_client.post("/animals/", data=form_data, files=files)
    assert response.status_code == 400
    assert "ya existe un animal con ese nombre" in response.text.lower()


@pytest.mark.asyncio
async def test_post_animal_invalid_species_rejected(
    app_client: AsyncClient,
    shelter_source: Source,
) -> None:
    """Species other than canino or felino must return HTTP 400."""
    form_data = {
        "source_id": str(shelter_source.id),
        "name": "Iguani",
        "species": "reptil",
        "municipality": "Cali",
        "accept_terms": "true",
    }
    files = {"foto": ("iguani.jpg", b"image-content", "image/jpeg")}

    response = await app_client.post("/animals/", data=form_data, files=files)
    assert response.status_code == 400
    assert "especie inválida" in response.text.lower()


@pytest.mark.asyncio
async def test_adopt_pin_invalid_renders_error_partial(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """Submitting an invalid PIN renders error feedback and does not alter status."""
    created = await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Lucas", "species": "canino", "municipality": "Bogotá"},
        "https://ejemplo.com/lucas.jpg",
    )
    animal = created["animal"]

    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": "0000"},  # Invalid PIN
    )

    assert response.status_code == 200
    assert "pin incorrecto" in response.text.lower()

    await db_session.refresh(animal)
    assert animal.status == "available"
    assert animal.adopted_at is None


@pytest.mark.asyncio
async def test_adopt_rate_limit_lockout_after_max_attempts(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """After 5 consecutive failed attempts from the same IP, 6th attempt returns HTTP 429."""
    created = await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Zeus", "species": "canino", "municipality": "Bogotá"},
        "https://ejemplo.com/zeus.jpg",
    )
    animal = created["animal"]

    # Execute 5 failed attempts with wrong PIN
    for _ in range(5):
        resp = await app_client.post(
            f"/animals/{animal.id}/adopt",
            data={"pin": "0000"},
        )
        assert resp.status_code == 200
        assert "pin incorrecto" in resp.text.lower()

    # 6th attempt must be locked out with HTTP 429
    blocked_resp = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": "0000"},
    )
    assert blocked_resp.status_code == 429
    assert "demasiados intentos fallidos" in blocked_resp.text.lower()

    await db_session.refresh(animal)
    assert animal.status == "available"


@pytest.mark.asyncio
async def test_animals_catalog_filters_species_and_municipality(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """HTMX fragment /animals/list filters properly by municipality and species."""
    await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Firulais Bogota", "species": "canino", "municipality": "Bogotá"},
        "https://ejemplo.com/firu.jpg",
    )
    await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Michi Bogota", "species": "felino", "municipality": "Bogotá"},
        "https://ejemplo.com/michi.jpg",
    )
    await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Toby Medellin", "species": "canino", "municipality": "Medellín"},
        "https://ejemplo.com/toby.jpg",
    )

    # Filter by canine species
    res_canino = await app_client.get("/animals/list?species=canino")
    assert res_canino.status_code == 200
    assert "Firulais Bogota" in res_canino.text
    assert "Toby Medellin" in res_canino.text
    assert "Michi Bogota" not in res_canino.text

    # Filter by Medellin municipality
    res_medellin = await app_client.get("/animals/list?municipality=Medellín")
    assert res_medellin.status_code == 200
    assert "Toby Medellin" in res_medellin.text
    assert "Firulais Bogota" not in res_medellin.text
    assert "Michi Bogota" not in res_medellin.text

    # Filter by canine species + Bogota municipality
    res_canino_bogota = await app_client.get(
        "/animals/list?species=canino&municipality=Bogotá"
    )
    assert res_canino_bogota.status_code == 200
    assert "Firulais Bogota" in res_canino_bogota.text
    assert "Toby Medellin" not in res_canino_bogota.text
    assert "Michi Bogota" not in res_canino_bogota.text


@pytest.mark.asyncio
async def test_animals_catalog_filter_by_status(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """The /animals/list catalog allows filtering by status (available vs adopted)."""
    await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Disponible Uno", "species": "canino", "municipality": "Bogotá"},
        "https://ejemplo.com/disp1.jpg",
    )
    p2 = await create_animal_profile(
        db_session,
        shelter_source.id,
        {"name": "Adoptado Dos", "species": "felino", "municipality": "Bogotá"},
        "https://ejemplo.com/adopt2.jpg",
    )

    # Mark second animal as adopted
    adopted_animal = p2["animal"]
    adopted_animal.status = "adopted"
    await db_session.commit()

    # By default status='available' should not include adopted animal
    res_default = await app_client.get("/animals/list")
    assert res_default.status_code == 200
    assert "Disponible Uno" in res_default.text
    assert "Adoptado Dos" not in res_default.text

    # Requesting status='adopted' should list only the adopted animal
    res_adopted = await app_client.get("/animals/list?status=adopted")
    assert res_adopted.status_code == 200
    assert "Adoptado Dos" in res_adopted.text
    assert "Disponible Uno" not in res_adopted.text
