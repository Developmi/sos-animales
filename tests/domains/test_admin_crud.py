"""Contract and integration tests for Admin Panel CRUD operations.

Covers:
- Unauthenticated access rejection (401).
- Sources CRUD: list, get edit form, update source, delete/deactivate source.
- Sterilizations CRUD: list, get edit form, update campaign, delete/cancel campaign.
- Animals CRUD: list, get edit form, update animal, delete animal.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.animals.models import AnimalProfile
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.main import app


def create_admin_token() -> str:
    """Generate a valid admin JWT access token."""
    payload = {
        "sub": "admin",
        "exp": datetime.now(UTC) + timedelta(hours=2),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


@pytest_asyncio.fixture
async def admin_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient authenticated as admin via cookies."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    token = create_admin_token()
    cookies = {"access_token": token}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated client."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ── 1. Security & Authentication Checks ─────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_routes_require_authentication(unauth_client: AsyncClient) -> None:
    """Unauthenticated requests to admin CRUD endpoints must return 401 or redirect to login (302)."""
    routes = [
        ("GET", "/admin/sources"),
        ("GET", "/admin/sterilizations"),
        ("GET", "/admin/animals"),
        ("POST", "/admin/sources/1/edit"),
        ("POST", "/admin/sources/1/delete"),
        ("POST", "/admin/sterilizations/campaigns/1/edit"),
        ("POST", "/admin/sterilizations/campaigns/1/delete"),
        ("POST", "/admin/animals/1/edit"),
        ("POST", "/admin/animals/1/delete"),
    ]
    for method, path in routes:
        if method == "GET":
            resp = await unauth_client.get(path)
        else:
            resp = await unauth_client.post(path, data={})
        assert resp.status_code in (401, 302), (
            f"{method} {path} allowed unauthorized access with {resp.status_code}"
        )
        if resp.status_code == 302:
            assert "/auth/login" in resp.headers.get("location", "")


# ── 2. Sources CRUD ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_sources_list_and_update(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Admin can list and update a foundation/source."""
    source = Source(
        name="Fundación Esperanza",
        type="verified_shelter",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="esperanza@example.com",
        contact_whatsapp="+573101112233",
        status="pending",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    # 1. List sources
    list_resp = await admin_client.get("/admin/sources")
    assert list_resp.status_code == 200
    assert "Fundación Esperanza" in list_resp.text

    # 2. Get edit form
    edit_form_resp = await admin_client.get(f"/admin/sources/{source.id}/edit")
    assert edit_form_resp.status_code == 200
    assert "Fundación Esperanza" in edit_form_resp.text
    assert "form" in edit_form_resp.text.lower()

    # 3. Submit edit
    update_data = {
        "name": "Fundación Esperanza Renacida",
        "type": "rescue_network",
        "municipality": "Medellín",
        "department": "Antioquia",
        "contact_email": "nueva_esperanza@example.com",
        "contact_whatsapp": "+573009998877",
        "status": "verified",
        "is_active": "true",
    }
    post_resp = await admin_client.post(
        f"/admin/sources/{source.id}/edit", data=update_data
    )
    assert post_resp.status_code in (200, 303)

    # Verify database was updated
    await db_session.refresh(source)
    assert source.name == "Fundación Esperanza Renacida"
    assert source.type == "rescue_network"
    assert source.municipality == "Medellín"
    assert source.status == "verified"


@pytest.mark.asyncio
async def test_admin_sources_delete_deactivates_or_removes(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Admin can delete/deactivate a foundation."""
    source = Source(
        name="Fundación Para Borrar",
        type="verified_shelter",
        municipality="Cali",
        department="Valle del Cauca",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    del_resp = await admin_client.post(f"/admin/sources/{source.id}/delete")
    assert del_resp.status_code in (200, 303)

    # Check that source is either deleted or marked inactive
    res = await db_session.execute(select(Source).where(Source.id == source.id))
    s = res.scalar_one_or_none()
    assert s is None or s.is_active is False or s.status == "inactive"


# ── 3. Sterilizations CRUD ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_sterilizations_list_update_delete(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Admin can list, edit, and cancel/delete a sterilization campaign."""
    source = Source(
        name="Clínica Animalia",
        type="veterinary_clinic",
        municipality="Bogotá",
        department="Cundinamarca",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    campaign = Campaign(
        source_id=source.id,
        title="Jornada Masiva Norte",
        municipality="Bogotá",
        address="Calle 100 # 15-20",
        lat=4.685,
        lng=-74.055,
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(days=1),
        species=["canino", "felino"],
        capacity=50,
        status="scheduled",
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)

    # 1. List campaigns
    list_resp = await admin_client.get("/admin/sterilizations")
    assert list_resp.status_code == 200
    assert "Jornada Masiva Norte" in list_resp.text

    # 2. Get edit form
    edit_form_resp = await admin_client.get(
        f"/admin/sterilizations/campaigns/{campaign.id}/edit"
    )
    assert edit_form_resp.status_code == 200
    assert "Jornada Masiva Norte" in edit_form_resp.text

    # 3. Update campaign
    edit_data = {
        "title": "Jornada Masiva Norte Modificada",
        "address": "Calle 100 # 20-30",
        "capacity": "100",
        "requirements": "Ayuno de 8 horas previo.",
        "status": "completed",
    }
    update_resp = await admin_client.post(
        f"/admin/sterilizations/campaigns/{campaign.id}/edit",
        data=edit_data,
    )
    assert update_resp.status_code in (200, 303)

    await db_session.refresh(campaign)
    assert campaign.title == "Jornada Masiva Norte Modificada"
    assert campaign.capacity == 100
    assert campaign.status == "completed"

    # 4. Delete / cancel campaign
    del_resp = await admin_client.post(
        f"/admin/sterilizations/campaigns/{campaign.id}/delete"
    )
    assert del_resp.status_code in (200, 303)

    res = await db_session.execute(select(Campaign).where(Campaign.id == campaign.id))
    c = res.scalar_one_or_none()
    assert c is None or c.status == "cancelled"


# ── 4. Animals CRUD ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_animals_list_update_delete(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Admin can list, edit, and delete an animal profile."""
    source = Source(
        name="Refugio San Roque",
        type="verified_shelter",
        municipality="Bucaramanga",
        department="Santander",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    animal = AnimalProfile(
        source_id=source.id,
        name="Pirata",
        species="canino",
        municipality="Bucaramanga",
        foto_url="https://r2.sos-animales.org/pirata.jpg",
        description="Perrito tuerto muy cariñoso.",
        status="available",
        is_sterilized=False,
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    # 1. List animals
    list_resp = await admin_client.get("/admin/animals")
    assert list_resp.status_code == 200
    assert "Pirata" in list_resp.text

    # 2. Get edit form
    edit_resp = await admin_client.get(f"/admin/animals/{animal.id}/edit")
    assert edit_resp.status_code == 200
    assert "Pirata" in edit_resp.text

    # 3. Update animal
    update_data = {
        "name": "Capitán Pirata",
        "species": "canino",
        "municipality": "Bucaramanga",
        "description": "Ya fue esterilizado y rehabilitado.",
        "status": "adopted",
        "is_sterilized": "true",
    }
    post_resp = await admin_client.post(
        f"/admin/animals/{animal.id}/edit", data=update_data
    )
    assert post_resp.status_code in (200, 303)

    await db_session.refresh(animal)
    assert animal.name == "Capitán Pirata"
    assert animal.status == "adopted"
    assert animal.is_sterilized is True

    # 4. Delete animal
    del_resp = await admin_client.post(f"/admin/animals/{animal.id}/delete")
    assert del_resp.status_code in (200, 303)

    res = await db_session.execute(
        select(AnimalProfile).where(AnimalProfile.id == animal.id)
    )
    a = res.scalar_one_or_none()
    assert a is None
