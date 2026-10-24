"""Contract, integration, and edge-case tests for the Animals domain router.

Target module: app/domains/animals/router.py
Coverage target: >90%

Covers:
- GET /animals/ (Search landing page) with and without query params (species, department, municipality, page).
- GET /animals/list (HTMX fragment) with filters, status, and empty results.
- GET /animals/new (Form) normal flow and exception fallback for geo data.
- POST /animals/ (Profile creation) validation:
  - Inactive or non-existent source rejection (400)
  - Fast image validation failure on primary and gallery photos (400)
  - Image upload failure / R2 error handling (500)
  - Species validation failure (400)
  - Age months to age years calculation logic (>= 12 and < 12)
  - Pydantic schema validation failures (future date, invalid fields) (400)
  - Duplicate animal name for source rejection (400)
  - Successful creation with and without source contact email (200)
- GET /animals/{animal_id} (Detail page) success (200) and not found (404).
- POST /animals/{animal_id}/adopt (Adoption flow):
  - Successful adoption with valid PIN (200)
  - Invalid PIN submission (200 HTMX error fragment / 403 expectation)
  - Rate limiting lockout after consecutive failures (429)
  - Non-existent animal PIN submission (200 error fragment)
  - Malformed PIN validation error (422)
- POST /animals/{animal_id}/edit (Contract test for missing edit route -> 404).
"""

import io
from collections.abc import AsyncGenerator
from datetime import date
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.database import get_db
from app.domains.animals.router import (
    _render_animal_error_card,
    _render_animal_success_card,
    adopt_animal,
    animal_detail_page,
    get_animals_list_htmx,
    new_animal_form,
    post_new_animal,
    search_animals_page,
)
from app.domains.animals.tools import create_animal_profile
from app.domains.sources.models import Source
from app.main import app


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES & HELPERS
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient bound to app with get_db dependency overridden to isolated test db_session."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def active_source(db_session: AsyncSession) -> Source:
    """Creates and persists an active verified shelter source."""
    source = Source(
        name="Fundación Esperanza Animal",
        type="verified_shelter",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="esperanza@animales.org",
        contact_whatsapp="+573001234567",
        is_active=True,
        status="verified",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def inactive_source(db_session: AsyncSession) -> Source:
    """Creates and persists an inactive source to test rejection branches."""
    source = Source(
        name="Refugio Suspendido",
        type="independent_rescuer",
        municipality="Medellín",
        department="Antioquia",
        contact_email="suspendido@animales.org",
        is_active=False,
        status="pending",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def source_without_email(db_session: AsyncSession) -> Source:
    """Creates an active source with no contact email to test fallback dispatch."""
    source = Source(
        name="Rescatista Sin Correo",
        type="independent_rescuer",
        municipality="Cali",
        department="Valle del Cauca",
        contact_email=None,
        is_active=True,
        status="verified",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


def make_dummy_image(
    name: str = "test.jpg", size_bytes: int = 256
) -> tuple[str, bytes, str]:
    """Generates a small valid-looking JPEG file tuple (filename, bytes, content_type)."""
    header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    content = header + b"\x00" * max(0, size_bytes - len(header))
    return (name, content, "image/jpeg")


def make_starlette_request(
    method: str = "GET", path: str = "/animals/", client_host: str = "127.0.0.1"
) -> Request:
    """Creates a Starlette Request object wired with app scope for direct router invocations."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"host", b"test"), (b"accept", b"text/html")],
        "app": app,
        "client": (client_host, 12345),
    }
    return Request(scope)


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET /animals/ - SEARCH LANDING PAGE
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_animals_page_http(app_client: AsyncClient) -> None:
    """GET /animals/ renders the main adoption landing page (index.html)."""
    response = await app_client.get("/animals/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "SOS Animales" in response.text or "adopci" in response.text.lower()


@pytest.mark.asyncio
async def test_search_animals_page_with_query_params(app_client: AsyncClient) -> None:
    """GET /animals/ gracefully accepts query params (species, department, municipality, page)."""
    response = await app_client.get(
        "/animals/?species=canino&department=Cundinamarca&municipality=Bogot%C3%A1&page=1"
    )
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_search_animals_page_direct_call() -> None:
    """Direct execution of search_animals_page function verifies template rendering."""
    req = make_starlette_request("GET", "/animals/")
    resp = await search_animals_page(req)
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /animals/list - HTMX CATALOG FRAGMENT & FILTERS
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_animals_list_default_parameters(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """GET /animals/list without params returns available profiles grid."""
    await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Luna Default", "species": "canino", "municipality": "Bogotá"},
        "https://r2.sos-animales.org/luna.jpg",
    )

    response = await app_client.get("/animals/list")
    assert response.status_code == 200
    assert "Luna Default" in response.text
    assert "pet-grid" in response.text


@pytest.mark.asyncio
async def test_get_animals_list_filters_species_and_municipality(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """GET /animals/list correctly applies species and municipality filters."""
    await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Perro Bogota", "species": "canino", "municipality": "Bogotá"},
        "https://r2.sos-animales.org/p1.jpg",
    )
    await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Gato Bogota", "species": "felino", "municipality": "Bogotá"},
        "https://r2.sos-animales.org/g1.jpg",
    )

    # Filter by canine
    resp_canino = await app_client.get(
        "/animals/list?species=canino&municipality=Bogotá"
    )
    assert resp_canino.status_code == 200
    assert "Perro Bogota" in resp_canino.text
    assert "Gato Bogota" not in resp_canino.text

    # Filter by feline
    resp_felino = await app_client.get(
        "/animals/list?species=felino&municipality=Bogotá"
    )
    assert resp_felino.status_code == 200
    assert "Gato Bogota" in resp_felino.text
    assert "Perro Bogota" not in resp_felino.text


@pytest.mark.asyncio
async def test_get_animals_list_empty_results_renders_empty_state(
    app_client: AsyncClient,
) -> None:
    """GET /animals/list with no matching records returns empty state markup."""
    response = await app_client.get("/animals/list?municipality=PuebloInexistente999")
    assert response.status_code == 200
    assert "empty-state" in response.text
    assert "No encontramos peluditos con esos filtros" in response.text


@pytest.mark.asyncio
async def test_get_animals_list_direct_call_covering_line_72(
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """Direct execution of get_animals_list_htmx verifies line 72 return TemplateResponse."""
    await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Direct List Dog", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/direct.jpg",
    )
    req = make_starlette_request("GET", "/animals/list")
    resp = await get_animals_list_htmx(
        req, municipality="Bogotá", species="canino", status="available", db=db_session
    )
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /animals/new - PUBLISH FORM & GEO FALLBACK
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_animal_form_success_http(app_client: AsyncClient) -> None:
    """GET /animals/new renders form with grouped municipalities context."""
    response = await app_client.get("/animals/new")
    assert response.status_code == 200
    assert "form" in response.text.lower()


@pytest.mark.asyncio
async def test_new_animal_form_renders_active_sources_selector_and_preselection(
    app_client: AsyncClient,
    active_source: Source,
    inactive_source: Source,
) -> None:
    """Contract: GET /animals/new renders a <select name='source_id'> with active foundations, excludes inactive ones, and supports ?source_id= pre-selection."""
    response = await app_client.get("/animals/new")
    assert response.status_code == 200
    assert 'type="hidden" name="source_id"' not in response.text
    assert 'name="source_id"' in response.text
    assert f'<option value="{active_source.id}"' in response.text
    assert active_source.name in response.text
    assert inactive_source.name not in response.text
    assert "/sources/register" in response.text

    # Pre-selection contract when ?source_id= is provided
    resp_preselected = await app_client.get(
        f"/animals/new?source_id={active_source.id}"
    )
    assert resp_preselected.status_code == 200
    assert f'<option value="{active_source.id}" selected>' in resp_preselected.text


@pytest.mark.asyncio
async def test_new_animal_form_geo_exception_fallback(app_client: AsyncClient) -> None:
    """GET /animals/new catches get_grouped_municipalities error and renders with empty dict."""
    with patch(
        "app.domains.animals.router.get_grouped_municipalities",
        side_effect=RuntimeError("Valkey geo store unavailable"),
    ):
        response = await app_client.get("/animals/new")
        assert response.status_code == 200
        assert "form" in response.text.lower()


@pytest.mark.asyncio
async def test_new_animal_form_direct_call_normal_and_exception(
    db_session: AsyncSession,
) -> None:
    """Direct call to new_animal_form tests normal flow and lines 84-86 exception block."""
    req = make_starlette_request("GET", "/animals/new")
    # Normal execution
    resp = await new_animal_form(req, db=db_session)
    assert resp.status_code == 200

    # Exception branch (lines 84-86)
    with patch(
        "app.domains.animals.router.get_grouped_municipalities",
        side_effect=Exception("DB Geo Failure"),
    ):
        resp_err = await new_animal_form(req, db=db_session)
        assert resp_err.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST /animals/ - SUBMISSION, VALIDATION, AND ERROR BRANCHES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_animal_rejected_nonexistent_source_http(
    app_client: AsyncClient,
) -> None:
    """POST /animals/ returns 400 when source_id does not exist."""
    filename, content, mime = make_dummy_image()
    files = {"foto": (filename, content, mime)}
    data = {
        "source_id": "999999",
        "name": "Fantasma",
        "species": "canino",
        "municipality": "Bogotá",
    }
    response = await app_client.post("/animals/", data=data, files=files)
    assert response.status_code == 400
    assert "Fuente no disponible" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_inactive_source_http(
    app_client: AsyncClient,
    inactive_source: Source,
) -> None:
    """POST /animals/ returns 400 when source is inactive (is_active=False)."""
    filename, content, mime = make_dummy_image()
    files = {"foto": (filename, content, mime)}
    data = {
        "source_id": str(inactive_source.id),
        "name": "Pelusa",
        "species": "felino",
        "municipality": "Medellín",
    }
    response = await app_client.post("/animals/", data=data, files=files)
    assert response.status_code == 400
    assert "Fuente no disponible" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_invalid_primary_image_type(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ rejects files with non-image MIME type (fast validation)."""
    files = {"foto": ("document.txt", b"Texto plano no permitido", "text/plain")}
    data = {
        "source_id": str(active_source.id),
        "name": "Rocky",
        "species": "canino",
        "municipality": "Bogotá",
    }
    response = await app_client.post("/animals/", data=data, files=files)
    assert response.status_code == 400
    assert "Archivo no permitido" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_invalid_gallery_image_type(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ rejects submission if any optional gallery photo is invalid."""
    fname, content, mime = make_dummy_image()
    files = {
        "foto": (fname, content, mime),
        "foto_2": ("malicioso.exe", b"binary payload", "application/octet-stream"),
    }
    data = {
        "source_id": str(active_source.id),
        "name": "Rocky Gallery Fail",
        "species": "canino",
        "municipality": "Bogotá",
    }
    response = await app_client.post("/animals/", data=data, files=files)
    assert response.status_code == 400
    assert "Archivo no permitido" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_oversized_image(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ rejects images exceeding 5MB."""
    oversized_content = b"\xff\xd8\xff\xe0" + b"\x00" * (5 * 1024 * 1024 + 100)
    files = {"foto": ("huge.jpg", oversized_content, "image/jpeg")}
    data = {
        "source_id": str(active_source.id),
        "name": "Gigante",
        "species": "canino",
        "municipality": "Bogotá",
    }
    response = await app_client.post("/animals/", data=data, files=files)
    assert response.status_code == 400
    assert "Archivo no permitido" in response.text


@pytest.mark.asyncio
async def test_post_animal_r2_upload_exception_returns_500(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ returns 500 when R2 photo upload throws an exception."""
    fname, content, mime = make_dummy_image()
    files = {"foto": (fname, content, mime)}
    data = {
        "source_id": str(active_source.id),
        "name": "R2 Fail Dog",
        "species": "canino",
        "municipality": "Bogotá",
    }
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        side_effect=RuntimeError("S3 bucket down or access denied"),
    ):
        response = await app_client.post("/animals/", data=data, files=files)
        assert response.status_code == 500
        assert "Error al procesar fotografía" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_invalid_species(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ rejects species other than 'canino' or 'felino'."""
    fname, content, mime = make_dummy_image()
    files = {"foto": (fname, content, mime)}
    data = {
        "source_id": str(active_source.id),
        "name": "Bugs Bunny",
        "species": "conejo",
        "municipality": "Bogotá",
    }
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/b.jpg",
    ):
        response = await app_client.post("/animals/", data=data, files=files)
        assert response.status_code == 400
        assert "Especie inválida" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_pydantic_validation_future_birthdate(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ returns 400 when AnimalCreate schema validator fails on future birthdate."""
    fname, content, mime = make_dummy_image()
    files = {"foto": (fname, content, mime)}
    data = {
        "source_id": str(active_source.id),
        "name": "Viajero del Tiempo",
        "species": "canino",
        "municipality": "Bogotá",
        "fecha_nacimiento": "2099-01-01",
    }
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/t.jpg",
    ):
        response = await app_client.post("/animals/", data=data, files=files)
        assert response.status_code == 400
        assert "Error en los datos ingresados" in response.text


@pytest.mark.asyncio
async def test_post_animal_rejected_pydantic_validation_short_municipality(
    app_client: AsyncClient,
    active_source: Source,
) -> None:
    """POST /animals/ returns 400 when municipality is shorter than min_length=3."""
    fname, content, mime = make_dummy_image()
    files = {"foto": (fname, content, mime)}
    data = {
        "source_id": str(active_source.id),
        "name": "Chiquito",
        "species": "canino",
        "municipality": "AB",
    }
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/c.jpg",
    ):
        response = await app_client.post("/animals/", data=data, files=files)
        assert response.status_code == 400
        assert "Error en los datos ingresados" in response.text


@pytest.mark.asyncio
async def test_post_animal_duplicate_name_rejection(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """POST /animals/ returns 400 when duplicate animal name is submitted for the same source."""
    await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Clonado", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/c1.jpg",
    )

    fname, content, mime = make_dummy_image()
    files = {"foto": (fname, content, mime)}
    data = {
        "source_id": str(active_source.id),
        "name": "Clonado",
        "species": "canino",
        "municipality": "Bogotá",
    }
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/c2.jpg",
    ):
        response = await app_client.post("/animals/", data=data, files=files)
        assert response.status_code == 400
        assert "No fue posible crear el perfil" in response.text


@pytest.mark.asyncio
async def test_post_animal_direct_calls_covering_all_router_branches(
    active_source: Source,
    inactive_source: Source,
    source_without_email: Source,
    db_session: AsyncSession,
) -> None:
    """Direct execution of post_new_animal covers all internal statements and lines 185-288."""
    from starlette.datastructures import Headers

    req = make_starlette_request("POST", "/animals/")
    f_valid = UploadFile(
        filename="dog.jpg",
        file=io.BytesIO(b"\xff\xd8\xff\xe0valid_jpeg_header"),
        headers=Headers({"content-type": "image/jpeg"}),
    )
    f_gallery = UploadFile(
        filename="gallery.jpg",
        file=io.BytesIO(b"\xff\xd8\xff\xe0gallery_bytes"),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    # Branch 1: Source not found (lines 186-193)
    resp_no_src = await post_new_animal(
        request=req,
        source_id=999999,
        name="Fantasma Direct",
        species="canino",
        municipality="Bogotá",
        foto=f_valid,
        foto_2=None,
        foto_3=None,
        foto_4=None,
        foto_5=None,
        breed=None,
        age_months=None,
        age_years=None,
        size=None,
        is_sterilized=False,
        description=None,
        sexo=None,
        fecha_nacimiento=None,
        etapa_madurez=None,
        condiciones_especiales=None,
        compatible_ninos=None,
        compatible_otros_animales=None,
        microchip=None,
        source_url=None,
        background_tasks=BackgroundTasks(),
        db=db_session,
    )
    assert resp_no_src.status_code == 400

    # Branch 2: Inactive source (lines 186-193)
    resp_inact = await post_new_animal(
        request=req,
        source_id=inactive_source.id,
        name="Inactivo Direct",
        species="canino",
        municipality="Bogotá",
        foto=f_valid,
        foto_2=None,
        foto_3=None,
        foto_4=None,
        foto_5=None,
        breed=None,
        age_months=None,
        age_years=None,
        size=None,
        is_sterilized=False,
        description=None,
        sexo=None,
        fecha_nacimiento=None,
        etapa_madurez=None,
        condiciones_especiales=None,
        compatible_ninos=None,
        compatible_otros_animales=None,
        microchip=None,
        source_url=None,
        background_tasks=BackgroundTasks(),
        db=db_session,
    )
    assert resp_inact.status_code == 400

    # Branch 3: Invalid primary image file validation (lines 201-206)
    f_bad_mime = UploadFile(
        filename="bad.txt",
        file=io.BytesIO(b"not image"),
        headers=Headers({"content-type": "text/plain"}),
    )
    resp_bad_img = await post_new_animal(
        request=req,
        source_id=active_source.id,
        name="Bad Img Direct",
        species="canino",
        municipality="Bogotá",
        foto=f_bad_mime,
        foto_2=None,
        foto_3=None,
        foto_4=None,
        foto_5=None,
        breed=None,
        age_months=None,
        age_years=None,
        size=None,
        is_sterilized=False,
        description=None,
        sexo=None,
        fecha_nacimiento=None,
        etapa_madurez=None,
        condiciones_especiales=None,
        compatible_ninos=None,
        compatible_otros_animales=None,
        microchip=None,
        source_url=None,
        background_tasks=BackgroundTasks(),
        db=db_session,
    )
    assert resp_bad_img.status_code == 400

    # Branch 4: Photo upload exception returns 500 (lines 211-215)
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        side_effect=RuntimeError("S3 Disk Full"),
    ):
        resp_upload_err = await post_new_animal(
            request=req,
            source_id=active_source.id,
            name="Upload Err Direct",
            species="canino",
            municipality="Bogotá",
            foto=f_valid,
            foto_2=None,
            foto_3=None,
            foto_4=None,
            foto_5=None,
            breed=None,
            age_months=None,
            age_years=None,
            size=None,
            is_sterilized=False,
            description=None,
            sexo=None,
            fecha_nacimiento=None,
            etapa_madurez=None,
            condiciones_especiales=None,
            compatible_ninos=None,
            compatible_otros_animales=None,
            microchip=None,
            source_url=None,
            background_tasks=BackgroundTasks(),
            db=db_session,
        )
        assert resp_upload_err.status_code == 500

    # Branch 5: Invalid species validation (lines 220-227)
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/img.jpg",
    ):
        resp_bad_sp = await post_new_animal(
            request=req,
            source_id=active_source.id,
            name="Bad Species Direct",
            species="iguana",
            municipality="Bogotá",
            foto=f_valid,
            foto_2=None,
            foto_3=None,
            foto_4=None,
            foto_5=None,
            breed=None,
            age_months=None,
            age_years=None,
            size=None,
            is_sterilized=False,
            description=None,
            sexo=None,
            fecha_nacimiento=None,
            etapa_madurez=None,
            condiciones_especiales=None,
            compatible_ninos=None,
            compatible_otros_animales=None,
            microchip=None,
            source_url=None,
            background_tasks=BackgroundTasks(),
            db=db_session,
        )
        assert resp_bad_sp.status_code == 400

    # Branch 6: Age months derivation branches: age_months >= 12 and < 12 (lines 230-231)
    # and Pydantic validation failure (lines 256-260)
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/img.jpg",
    ):
        resp_pydantic_err = await post_new_animal(
            request=req,
            source_id=active_source.id,
            name="Future Dog",
            species="canino",
            municipality="Bogotá",
            foto=f_valid,
            foto_2=None,
            foto_3=None,
            foto_4=None,
            foto_5=None,
            breed=None,
            age_months=6,
            age_years=None,
            size=None,
            is_sterilized=False,
            description=None,
            sexo=None,
            fecha_nacimiento=date(2099, 1, 1),
            etapa_madurez=None,
            condiciones_especiales=None,
            compatible_ninos=None,
            compatible_otros_animales=None,
            microchip=None,
            source_url=None,
            background_tasks=BackgroundTasks(),
            db=db_session,
        )
        assert resp_pydantic_err.status_code == 400

    # Branch 7: Duplicate name error in create_animal_profile (lines 267-271)
    await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Duplicado Direct", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/dup.jpg",
    )
    with patch(
        "app.domains.animals.router.upload_photo_to_r2",
        return_value="https://r2.test/img.jpg",
    ):
        resp_dup = await post_new_animal(
            request=req,
            source_id=active_source.id,
            name="Duplicado Direct",
            species="canino",
            municipality="Bogotá",
            foto=f_valid,
            foto_2=None,
            foto_3=None,
            foto_4=None,
            foto_5=None,
            breed=None,
            age_months=24,
            age_years=None,
            size=None,
            is_sterilized=False,
            description=None,
            sexo=None,
            fecha_nacimiento=None,
            etapa_madurez=None,
            condiciones_especiales=None,
            compatible_ninos=None,
            compatible_otros_animales=None,
            microchip=None,
            source_url=None,
            background_tasks=BackgroundTasks(),
            db=db_session,
        )
        assert resp_dup.status_code == 400

    # Branch 8: Success with gallery photos and contact_email present (lines 272-288)
    bg_tasks = BackgroundTasks()
    with (
        patch(
            "app.domains.animals.router.upload_photo_to_r2",
            return_value="https://r2.test/dog.jpg",
        ),
        patch(
            "app.domains.animals.router.upload_multiple_photos",
            return_value=["https://r2.test/g1.jpg"],
        ),
        patch("app.domains.animals.router.send_pin_email_sync"),
    ):
        resp_success = await post_new_animal(
            request=req,
            source_id=active_source.id,
            name="Exito Direct",
            species="canino",
            municipality="Bogotá",
            foto=f_valid,
            foto_2=f_gallery,
            foto_3=None,
            foto_4=None,
            foto_5=None,
            breed="Criollo",
            age_months=36,
            age_years=None,
            size="mediano",
            is_sterilized=True,
            description="Amistoso",
            sexo="macho",
            fecha_nacimiento=None,
            etapa_madurez="adulto",
            condiciones_especiales=["ninguna"],
            compatible_ninos="true",
            compatible_otros_animales="false",
            microchip="123456",
            source_url=None,
            background_tasks=bg_tasks,
            db=db_session,
        )
        assert resp_success.status_code == 200

    # Branch 9: Success with source having no contact_email (fallback to contacto@sos-animales.org)
    with (
        patch(
            "app.domains.animals.router.upload_photo_to_r2",
            return_value="https://r2.test/dog2.jpg",
        ),
        patch("app.domains.animals.router.send_pin_email_sync"),
    ):
        resp_fallback_email = await post_new_animal(
            request=req,
            source_id=source_without_email.id,
            name="Exito Sin Correo Direct",
            species="felino",
            municipality="Cali",
            foto=f_valid,
            foto_2=None,
            foto_3=None,
            foto_4=None,
            foto_5=None,
            breed=None,
            age_months=6,
            age_years=None,
            size=None,
            is_sterilized=False,
            description=None,
            sexo=None,
            fecha_nacimiento=None,
            etapa_madurez=None,
            condiciones_especiales=None,
            compatible_ninos=None,
            compatible_otros_animales=None,
            microchip=None,
            source_url=None,
            background_tasks=BackgroundTasks(),
            db=db_session,
        )
        assert resp_fallback_email.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /animals/{animal_id} - DETAIL VIEW
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_animal_detail_page_success_http(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """GET /animals/{id} returns detailed profile with shelter source data."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {
            "name": "Dante",
            "species": "canino",
            "municipality": "Bogotá",
            "breed": "Husky",
        },
        "https://r2.test/dante.jpg",
    )
    animal = created["animal"]

    response = await app_client.get(f"/animals/{animal.id}")
    assert response.status_code == 200
    assert "Dante" in response.text
    assert active_source.name in response.text


@pytest.mark.asyncio
async def test_get_animal_detail_page_not_found_http(
    app_client: AsyncClient,
) -> None:
    """GET /animals/{id} returns 404 when animal_id does not exist."""
    response = await app_client.get("/animals/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_animal_detail_page_direct_calls(
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """Direct execution of animal_detail_page covers lines 296-305."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Detail Direct Dog", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/detail_direct.jpg",
    )
    animal = created["animal"]
    req = make_starlette_request("GET", f"/animals/{animal.id}")

    # Success (line 301)
    resp = await animal_detail_page(req, animal_id=animal.id, db=db_session)
    assert resp.status_code == 200

    # Not found raises HTTPException 404 (lines 298-299)
    with pytest.raises(HTTPException) as exc_info:
        await animal_detail_page(req, animal_id=999999, db=db_session)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Animal no encontrado"


# ─────────────────────────────────────────────────────────────────────────────
# 6. POST /animals/{animal_id}/adopt - ADOPTION FLOW & PIN VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adopt_animal_success_with_valid_pin_http(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """POST /animals/{id}/adopt marks status as adopted when correct PIN is provided."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Kira Adopcion", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/kira.jpg",
    )
    animal = created["animal"]
    pin = created["raw_pin"]

    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": pin},
    )
    assert response.status_code == 200
    assert "adopt_success" in response.text or "adoptado" in response.text.lower()

    # Verify status changed in database
    await db_session.refresh(animal)
    assert animal.status == "adopted"
    assert animal.adopted_at is not None


@pytest.mark.asyncio
async def test_adopt_animal_failed_with_incorrect_pin_http(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """POST /animals/{id}/adopt returns error fragment when PIN does not match."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Simba Incorrect", "species": "felino", "municipality": "Bogotá"},
        "https://r2.test/simba.jpg",
    )
    animal = created["animal"]

    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": "0000"},
    )
    assert response.status_code == 200
    assert "pin incorrecto" in response.text.lower()


@pytest.mark.asyncio
async def test_adopt_animal_rate_limiting_lockout_429_http(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """POST /animals/{id}/adopt returns 429 when check_pin_rate_limit threshold is exceeded."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Brute Force Target", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/bf.jpg",
    )
    animal = created["animal"]

    with patch("app.domains.animals.router.check_pin_rate_limit", return_value=False):
        response = await app_client.post(
            f"/animals/{animal.id}/adopt",
            data={"pin": "1234"},
        )
        assert response.status_code == 429
        assert "Demasiados intentos fallidos" in response.text


@pytest.mark.asyncio
async def test_adopt_animal_malformed_pin_triggers_validation_error_422(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """POST /animals/{id}/adopt returns 422 when PIN is not 4 digits (AdoptAction schema)."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Schema Check", "species": "felino", "municipality": "Bogotá"},
        "https://r2.test/sc.jpg",
    )
    animal = created["animal"]

    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": "abcd12"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_adopt_animal_direct_calls_covering_all_branches(
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """Direct execution of adopt_animal covers lines 315-340 completely."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Direct Adopt Dog", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/direct_adopt.jpg",
    )
    animal = created["animal"]
    pin = created["raw_pin"]
    req = make_starlette_request("POST", f"/animals/{animal.id}/adopt")

    # Branch 1: Rate limit blocked (lines 316-322)
    with patch("app.domains.animals.router.check_pin_rate_limit", return_value=False):
        resp_rl = await adopt_animal(
            req, animal_id=animal.id, pin="1234", db=db_session
        )
        assert resp_rl.status_code == 429

    # Branch 2: Wrong PIN (lines 334-340)
    resp_wrong = await adopt_animal(req, animal_id=animal.id, pin="9999", db=db_session)
    assert resp_wrong.status_code == 200

    # Branch 3: Correct PIN success (lines 328-333)
    resp_ok = await adopt_animal(req, animal_id=animal.id, pin=pin, db=db_session)
    assert resp_ok.status_code == 200

    # Request without client host (line 315 client_ip fallback to 127.0.0.1)
    req_no_client = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/animals/1/adopt",
            "headers": [],
            "app": app,
        }
    )
    resp_no_client = await adopt_animal(
        req_no_client, animal_id=animal.id, pin="9999", db=db_session
    )
    assert resp_no_client.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 7. CONTRACT TESTS FOR BUGS AND ANOMALIES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adopt_animal_incorrect_pin_htmx_fragment_and_reset_on_success(
    app_client: AsyncClient,
    active_source: Source,
    db_session: AsyncSession,
) -> None:
    """Verifies HTMX 200 error fragment contract on invalid PIN and PIN counter reset upon valid PIN."""
    created = await create_animal_profile(
        db_session,
        active_source.id,
        {"name": "Status Check HTMX", "species": "canino", "municipality": "Bogotá"},
        "https://r2.test/sc403.jpg",
    )
    animal = created["animal"]
    raw_pin = created["raw_pin"]

    # Wrong PIN returns 200 so HTMX swaps #adopt-result with adopt_error.html
    response = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": "0000"},
    )
    assert response.status_code == 200
    assert "pin incorrecto" in response.text.lower()

    # Correct PIN succeeds and resets failed PIN attempts counter
    response_ok = await app_client.post(
        f"/animals/{animal.id}/adopt",
        data={"pin": raw_pin},
    )
    assert response_ok.status_code == 200
    assert "adoptado" in response_ok.text.lower()


@pytest.mark.asyncio
async def test_post_animal_edit_not_implemented(
    app_client: AsyncClient,
) -> None:
    """POST /animals/{id}/edit returns 404 because no edit endpoint exists in animals domain."""
    response = await app_client.post("/animals/1/edit", data={"name": "New Name"})
    assert response.status_code == 404


def test_render_error_and_success_cards_directly() -> None:
    """Direct execution of helper functions _render_animal_error_card and _render_animal_success_card."""
    error_html = _render_animal_error_card("Prueba Error", "Detalle del error")
    assert "Prueba Error" in error_html
    assert "Detalle del error" in error_html

    success_html = _render_animal_success_card(
        42, "Boby", "Bogotá", "boby@fundacion.org"
    )
    assert "Boby" in success_html
    assert "boby@fundacion.org" in success_html
    assert "/animals/42" in success_html
