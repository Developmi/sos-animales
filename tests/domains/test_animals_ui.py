"""UI and template tests for the Animals domain (Lightbox, Gallery, and Terms validation)."""

from collections.abc import AsyncGenerator

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
        name="Albergue Refugio Peludos",
        type="verified_shelter",
        municipality="Medellín",
        department="Antioquia",
        contact_email="refugio@sos-animales.org",
        contact_whatsapp="+573001234567",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_animal_detail_has_lightbox_modal_and_trigger(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """Phase 2: Animal detail view must include an accessible lightbox modal for full-size photo viewing."""
    res = await create_animal_profile(
        db_session,
        shelter_source.id,
        {
            "name": "Luna",
            "species": "canino",
            "municipality": "Medellín",
            "description": "Perrita rescatada muy cariñosa.",
        },
        "https://r2.sos-animales.org/luna_main.jpg",
    )
    animal = res["animal"]

    resp = await app_client.get(f"/animals/{animal.id}")
    assert resp.status_code == 200
    html = resp.text

    # Must contain lightbox modal element
    assert "lightbox-modal" in html or 'id="lightbox-modal"' in html
    # Must contain zoom action trigger
    assert (
        "openLightbox" in html
        or "data-lightbox" in html
        or 'onclick="openLightbox' in html
    )
    # Must have close button with accessible aria-label
    assert (
        "Cerrar imagen" in html
        or "Cerrar modal" in html
        or 'aria-label="Cerrar' in html
    )


@pytest.mark.asyncio
async def test_animal_gallery_renders_all_photos_when_three_uploaded(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """Phase 3: When multiple photos are uploaded (e.g. 3), all 3 photos must be present in the thumbnail gallery."""
    res = await create_animal_profile(
        db_session,
        shelter_source.id,
        {
            "name": "Rocky",
            "species": "canino",
            "municipality": "Medellín",
            "description": "Cachorro juguetón.",
            "foto_urls": [
                "https://r2.sos-animales.org/rocky_extra1.jpg",
                "https://r2.sos-animales.org/rocky_extra2.jpg",
            ],
        },
        "https://r2.sos-animales.org/rocky_main.jpg",
    )
    animal = res["animal"]

    resp = await app_client.get(f"/animals/{animal.id}")
    assert resp.status_code == 200
    html = resp.text

    # Gallery thumbs container must exist
    assert 'class="gallery-thumbs"' in html
    # Extract the gallery-thumbs slice of HTML
    thumbs_section = (
        html.split('class="gallery-thumbs"')[1].split("</div>\n      {% endif %}")[0]
        if "gallery-thumbs" in html
        else ""
    )
    # All 3 photos must be inside gallery-thumbs
    assert "rocky_main.jpg" in thumbs_section, (
        "Main photo must be present in gallery thumbnails"
    )
    assert "rocky_extra1.jpg" in thumbs_section
    assert "rocky_extra2.jpg" in thumbs_section


@pytest.mark.asyncio
async def test_animal_gallery_renders_when_two_photos_uploaded(
    app_client: AsyncClient,
    shelter_source: Source,
    db_session: AsyncSession,
) -> None:
    """Phase 3: When 2 photos are uploaded (main + 1 extra), thumbnails must still render both."""
    res = await create_animal_profile(
        db_session,
        shelter_source.id,
        {
            "name": "Max",
            "species": "canino",
            "municipality": "Medellín",
            "description": "Perrito noble.",
            "foto_urls": [
                "https://r2.sos-animales.org/max_extra1.jpg",
            ],
        },
        "https://r2.sos-animales.org/max_main.jpg",
    )
    animal = res["animal"]

    resp = await app_client.get(f"/animals/{animal.id}")
    assert resp.status_code == 200
    html = resp.text

    # Gallery thumbs must render when 2 photos total exist
    assert 'class="gallery-thumbs"' in html
    assert "max_main.jpg" in html
    assert "max_extra1.jpg" in html


@pytest.mark.asyncio
async def test_animal_form_has_client_side_terms_validation(
    app_client: AsyncClient,
) -> None:
    """Phase 4: profile_form.html must validate pet-accept-terms in handleAnimalFormSubmit."""
    resp = await app_client.get("/animals/new")
    assert resp.status_code == 200
    html = resp.text

    assert "pet-accept-terms" in html
    assert "terms.checked" in html, (
        "handleAnimalFormSubmit must check terms.checked before submitting"
    )
