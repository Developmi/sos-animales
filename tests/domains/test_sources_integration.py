"""Integration tests for Sources (Shelters/Rescuers) and Veterinary Verification.

Covers:
1. Public profile rendering (/sources/{id}) with animals, campaigns, and normalized WhatsApp links.
2. Business logic verify_source() promoting shelters from pending to verified status.
3. Organization type validation during self-registration returning HTTP 400.
4. Directory listing filtering (/sources/) by municipality.
5. End-to-end veterinary inspection workflow promoting verified sources.
6. Rejection handling when veterinary criteria are not met.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
import jwt
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.config import settings
from app.database import get_db
from app.domains.sources.models import Source
from app.domains.sources.tools import register_source, verify_source
from app.domains.sources.schemas import SourceRegisterIn
from app.domains.animals.tools import create_animal_profile
from app.domains.sterilization.tools import create_new_campaign
from app.domains.verification.tools import create_verification_request, schedule_visit


def make_admin_token() -> str:
    return jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"access_token": make_admin_token()},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_foundation(db_session: AsyncSession) -> Source:
    reg_data = SourceRegisterIn(
        name="Fundación Amigos Peludos",
        type="verified_shelter",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="amigos@peludos.org",
        contact_whatsapp="+573108889900",
        contact_url="https://peludos.org",
    )
    source = await register_source(db_session, reg_data)
    return source


@pytest.mark.asyncio
async def test_source_profile_renders_animals_campaigns_and_normalized_whatsapp(
    app_client: AsyncClient,
    db_session: AsyncSession,
    sample_foundation: Source,
) -> None:
    """Validate that source profile renders its animals, campaigns, and normalizes WhatsApp without duplicate country codes."""
    # Create an animal for this source
    await create_animal_profile(
        db_session,
        sample_foundation.id,
        {"name": "Copito", "species": "felino", "municipality": "Bogotá"},
        "https://ejemplo.com/copito.jpg",
    )

    # Create a campaign for this source
    future_date = datetime.now(timezone.utc) + timedelta(days=6)
    await create_new_campaign(
        db_session,
        sample_foundation.id,
        {
            "title": "Campaña Esterilización Peludos",
            "municipality": "Bogotá",
            "starts_at": future_date,
            "species": ["canino", "felino"],
            "is_free": True,
        },
        address="Calle 100 # 15-20",
    )

    response = await app_client.get(f"/sources/{sample_foundation.id}")
    assert response.status_code == 200
    assert "Fundación Amigos Peludos" in response.text
    assert "Copito" in response.text
    assert "Campaña Esterilización Peludos" in response.text

    # WhatsApp normalization: must be wa.me/573108889900 and NEVER wa.me/5757...
    assert "wa.me/573108889900" in response.text
    assert "wa.me/5757" not in response.text


@pytest.mark.asyncio
async def test_verify_source_tool_promotes_source_to_verified(
    db_session: AsyncSession,
    sample_foundation: Source,
) -> None:
    """verify_source promotes a source from pending to verified and populates verified_at."""
    assert sample_foundation.status == "pending"
    assert sample_foundation.verified_at is None

    verified_source = await verify_source(db_session, sample_foundation.id)
    assert verified_source is not None
    assert verified_source.status == "verified"
    assert verified_source.verified_at is not None

    await db_session.refresh(sample_foundation)
    assert sample_foundation.status == "verified"


@pytest.mark.asyncio
async def test_sources_register_invalid_type_returns_400(
    app_client: AsyncClient,
) -> None:
    """Invalid organization type returns controlled HTTP 400 error."""
    form_data = {
        "name": "Comercializadora Ilegal",
        "type": "pet_shop_privada",  # Invalid type
        "municipality": "Bogotá",
        "department": "Cundinamarca",
        "accept_terms": "true",
    }
    response = await app_client.post("/sources/register", data=form_data)
    assert response.status_code == 400
    assert "error" in response.text.lower() or "inválido" in response.text.lower()


@pytest.mark.asyncio
async def test_sources_list_filters_by_municipality(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """The /sources directory filters active sources by municipality."""
    await register_source(
        db_session,
        SourceRegisterIn(
            name="Refugio Bogotá Norte",
            type="verified_shelter",
            municipality="Bogotá",
            department="Cundinamarca",
        ),
    )
    await register_source(
        db_session,
        SourceRegisterIn(
            name="Refugio Medellín Valle",
            type="verified_shelter",
            municipality="Medellín",
            department="Antioquia",
        ),
    )

    # Filter by Bogota
    res_bog = await app_client.get("/sources/?municipality=Bogotá")
    assert res_bog.status_code == 200
    assert "Refugio Bogotá Norte" in res_bog.text
    assert "Refugio Medellín Valle" not in res_bog.text


@pytest.mark.asyncio
async def test_verification_workflow_full_flow(
    app_client: AsyncClient,
    db_session: AsyncSession,
    sample_foundation: Source,
) -> None:
    """End-to-end veterinary inspection workflow: if all criteria pass, source becomes verified."""
    # 1. Create verification request
    req = await create_verification_request(
        db_session, sample_foundation.id, "Certificados veterinarios adjuntos"
    )

    # 2. Schedule visit
    visit_date = datetime.now(timezone.utc) + timedelta(days=1)
    visit = await schedule_visit(
        db_session,
        req.id,
        visit_type="presencial",
        scheduled_at=visit_date,
        visitor_name="Dra. Gómez (M.V.)",
    )

    # 3. Submit checklist with all passing criteria
    checklist_payload = {
        "crit_1": "true",
        "crit_2": "true",
        "crit_3": "true",
        "global_notes": "Instalaciones impecables y protocolos al día.",
    }
    resp = await app_client.post(
        f"/verification/visits/{visit.id}/checklist",
        data=checklist_payload,
    )
    assert resp.status_code == 200
    assert (
        "verificada" in resp.text.lower()
        or "aprobada" in resp.text.lower()
        or "éxito" in resp.text.lower()
    )

    # 4. Verify in DB that source transitioned to 'verified'
    await db_session.refresh(sample_foundation)
    assert sample_foundation.status == "verified"
    assert sample_foundation.verified_at is not None


@pytest.mark.asyncio
async def test_verification_workflow_rejected_when_criterion_fails(
    app_client: AsyncClient,
    db_session: AsyncSession,
    sample_foundation: Source,
) -> None:
    """If any veterinary criterion fails, source remains unverified."""
    req = await create_verification_request(db_session, sample_foundation.id)
    visit = await schedule_visit(
        db_session,
        req.id,
        visit_type="presencial",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        visitor_name="Dr. Pérez",
    )

    # Fail criterion 2 (veterinary records)
    checklist_payload = {
        "crit_1": "true",
        "crit_2": "false",
        "crit_3": "true",
        "global_notes": "Faltan carnets de vacunación.",
    }
    resp = await app_client.post(
        f"/verification/visits/{visit.id}/checklist",
        data=checklist_payload,
    )
    assert resp.status_code == 200

    await db_session.refresh(sample_foundation)
    assert sample_foundation.status != "verified"
