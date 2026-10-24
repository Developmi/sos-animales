"""Tests for animals domain tools and business logic.

Covers:
- create_animal_profile: profile creation with photo + PIN.
- list_animals_by_filters: filters by municipality, species, and status.
- get_animal_detail: detail retrieval with source relationship.
- mark_as_adopted: PIN verification and status transition.
- upload_photo_to_r2: R2 photo upload simulation.
"""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.animals.tools import (
    create_animal_profile,
    get_animal_detail,
    list_animals_by_filters,
    mark_as_adopted,
    upload_photo_to_r2,
)
from app.domains.sources.models import Source

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def sample_source(db_session: AsyncSession) -> Source:
    source = Source(
        name="Refugio Adopciones Test",
        type="verified_shelter",
        status="verified",
        municipality="Bogotá",
        department="Cundinamarca",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


# ── TC-01: Create animal profile ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_animal_profile_returns_animal_and_pin(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Creating a profile returns animal entity + 4-digit raw PIN."""
    data = {
        "name": "Luna",
        "species": "canino",
        "municipality": "Bogotá",
        "breed": "Criollo",
        "age_years": 2,
        "size": "mediano",
        "is_sterilized": False,
        "description": "Muy juguetona",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://ejemplo.com/foto.jpg"
    )

    assert "animal" in result
    assert "raw_pin" in result
    assert result["animal"].name == "Luna"
    assert result["animal"].species == "canino"
    assert result["animal"].status == "available"
    assert len(result["raw_pin"]) == 4
    assert result["raw_pin"].isdigit()


# ── TC-02: Create profile with governance fields ─────────────────────────────


@pytest.mark.asyncio
async def test_create_animal_profile_with_data_governance_fields(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Data governance fields (SDD-07) are properly persisted."""
    data = {
        "name": "Tom",
        "species": "felino",
        "municipality": "Medellín",
        "sexo": "macho",
        "fecha_nacimiento": date(2023, 6, 15),
        "etapa_madurez": "joven",
        "condiciones_especiales": ["ciego"],
        "compatible_ninos": True,
        "compatible_otros_animales": False,
        "microchip": "900123456789012",
        "data_origin": "official_authorized",
        "source_url": "https://datos.gov.co/animal/1",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://ejemplo.com/foto.jpg"
    )
    animal = result["animal"]

    assert animal.sexo == "macho"
    assert animal.etapa_madurez == "joven"
    assert animal.condiciones_especiales == ["ciego"]
    assert animal.compatible_ninos
    assert animal.data_origin == "official_authorized"


# ── TC-03: List animals by municipality ──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_animals_by_municipality(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Filtering by municipality returns only animals within that municipality."""
    data_bog = {
        "name": "Bogotano",
        "species": "canino",
        "municipality": "Bogotá",
    }
    data_med = {
        "name": "Medellinés",
        "species": "felino",
        "municipality": "Medellín",
    }
    await create_animal_profile(
        db_session, sample_source.id, data_bog, "https://ejemplo.com/1.jpg"
    )
    await create_animal_profile(
        db_session, sample_source.id, data_med, "https://ejemplo.com/2.jpg"
    )

    results = await list_animals_by_filters(db_session, municipality="Bogotá")
    assert len(results) >= 1
    assert all("Bogotá" in a.municipality for a in results)


# ── TC-04: List animals by species ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_animals_by_species(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Filtering by species returns only animals of that species."""
    data = {
        "name": "Canino Test",
        "species": "canino",
        "municipality": "Bogotá",
    }
    await create_animal_profile(
        db_session, sample_source.id, data, "https://ejemplo.com/foto.jpg"
    )

    results = await list_animals_by_filters(db_session, species="canino")
    assert all(a.species == "canino" for a in results)


# ── TC-05: List animals without results ───────────────────────────────────────


@pytest.mark.asyncio
async def test_list_animals_no_results(
    db_session: AsyncSession,
) -> None:
    """Filter without matches returns empty list."""
    results = await list_animals_by_filters(db_session, municipality="inexistente")
    assert results == []


# ── TC-06: Mark as adopted with correct PIN ──────────────────────────────────


@pytest.mark.asyncio
async def test_mark_as_adopted_with_correct_pin(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Correct PIN updates status to adopted and records adopted_at timestamp."""
    data = {
        "name": "Adoptable",
        "species": "canino",
        "municipality": "Bogotá",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://ejemplo.com/foto.jpg"
    )
    animal = result["animal"]
    pin = result["raw_pin"]

    success = await mark_as_adopted(db_session, animal.id, pin)
    assert success

    # Verify database update
    detail = await get_animal_detail(db_session, animal.id)
    assert detail is not None
    assert detail["animal"].status == "adopted"
    assert detail["animal"].adopted_at is not None


# ── TC-07: Mark as adopted with incorrect PIN ────────────────────────────────


@pytest.mark.asyncio
async def test_mark_as_adopted_with_wrong_pin(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Incorrect PIN does not change adoption status."""
    data = {
        "name": "No Adoptable",
        "species": "felino",
        "municipality": "Medellín",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://ejemplo.com/foto.jpg"
    )
    animal = result["animal"]

    success = await mark_as_adopted(db_session, animal.id, "0000")
    assert not success

    detail = await get_animal_detail(db_session, animal.id)
    assert detail is not None
    assert detail["animal"].status == "available"


# ── TC-08: Mark as adopted with nonexistent animal ────────────────────────────


@pytest.mark.asyncio
async def test_mark_as_adopted_nonexistent_animal(
    db_session: AsyncSession,
) -> None:
    """Non-existent animal ID returns False."""
    success = await mark_as_adopted(db_session, 99999, "1234")
    assert not success


# ── TC-09: Animal detail ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_animal_detail_returns_animal_and_source(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """get_animal_detail returns animal and associated source."""
    data = {
        "name": "Detallado",
        "species": "canino",
        "municipality": "Cali",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://ejemplo.com/foto.jpg"
    )
    animal_id = result["animal"].id

    detail = await get_animal_detail(db_session, animal_id)
    assert detail is not None
    assert detail["animal"].id == animal_id
    assert detail["source"].id == sample_source.id


# ── TC-10: Nonexistent animal detail ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_animal_detail_not_found(
    db_session: AsyncSession,
) -> None:
    """Non-existent ID returns None."""
    detail = await get_animal_detail(db_session, 99999)
    assert detail is None


# ── TC-11: upload_photo_to_r2 returns URL ────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_photo_to_r2_returns_url() -> None:
    """Simulates upload and validates returning a public URL."""
    from io import BytesIO

    from fastapi import UploadFile

    file = UploadFile(filename="test.jpg", file=BytesIO(b"fake-image-data"))
    url = await upload_photo_to_r2(file)

    assert url.startswith("https://via.placeholder.com/")
    assert ".jpg" in url or ".png" in url


# ── TC-12: validate_image_file strict checks ─────────────────────────────────


def test_validate_image_file_rejects_oversized_file() -> None:
    """Files over 5MB must be strictly rejected before any network/cloud upload."""
    from io import BytesIO

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from app.domains.animals.tools import validate_image_file

    oversized_data = b"0" * (5 * 1024 * 1024 + 10)
    file = UploadFile(
        filename="huge_photo.jpg",
        file=BytesIO(oversized_data),
        headers=Headers({"content-type": "image/jpeg"}),
    )
    with pytest.raises(ValueError, match="superando el límite máximo permitido de 5MB"):
        validate_image_file(file)


def test_validate_image_file_rejects_invalid_mime() -> None:
    """Non-image files must be rejected."""
    from io import BytesIO

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from app.domains.animals.tools import validate_image_file

    file = UploadFile(
        filename="document.pdf",
        file=BytesIO(b"fake-pdf"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(ValueError, match="no es una imagen válida"):
        validate_image_file(file)


@pytest.mark.asyncio
async def test_create_animal_profile_with_age_months(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """Animal profile correctly stores age_months for puppies/kittens."""
    data = {
        "name": "Cachorrito Toby",
        "species": "canino",
        "breed": "Criollo",
        "age_months": 3,
        "age_years": 0,
        "size": "pequeno",
        "is_sterilized": False,
        "description": "Cachorro juguetón de 3 meses rescatado.",
        "municipality": "Medellín",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://placeholder.com/toby.jpg"
    )
    animal = result["animal"]
    assert animal.id is not None
    assert animal.age_months == 3
    assert animal.name == "Cachorrito Toby"
