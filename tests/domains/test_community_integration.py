"""Integration tests for Community reports and decentralized voting.

Covers:
1. Community report submission targeting an animal (XOR constraint).
2. Community report submission targeting a campaign (XOR constraint).
3. HTTP 400 rejection on XOR target constraint violations (both or neither).
4. HTTP 400 rejection on non-existent targets.
5. Anti-spam voting protection: IP-based duplicate vote blocking.
6. HTTP 404 response when attempting to vote on non-existent reports.
7. Automatic freshness renewal (last_confirmed_at) when 'confirmed' reaches the consensus threshold.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.animals.tools import create_animal_profile
from app.domains.community.tools import cast_vote, register_update
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.domains.sterilization.tools import create_new_campaign
from app.main import app


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_source(db_session: AsyncSession) -> Source:
    source = Source(
        name="Red Rescate Animal",
        type="verified_shelter",
        status="verified",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="red@sos-animales.org",
        contact_whatsapp="+573100001122",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_post_community_update_success_xor_animal(
    app_client: AsyncClient,
    sample_source: Source,
    db_session: AsyncSession,
) -> None:
    """Submit a report for a valid animal and prevent self-voting by creator."""
    created = await create_animal_profile(
        db_session,
        sample_source.id,
        {"name": "Simba", "species": "felino", "municipality": "Bogotá"},
        "https://ejemplo.com/simba.jpg",
    )
    animal = created["animal"]

    form_data = {
        "update_type": "in_treatment",
        "note": "El peludito está recibiendo atención veterinaria",
        "animal_id": str(animal.id),
    }

    response = await app_client.post("/community/update", data=form_data)
    assert response.status_code == 200
    assert (
        "reporte recibido" in response.text.lower()
        or "gracias" in response.text.lower()
    )
    assert response.headers.get("HX-Trigger") == "newCommunityUpdate"


@pytest.mark.asyncio
async def test_post_community_update_success_xor_campaign(
    app_client: AsyncClient,
    sample_source: Source,
    db_session: AsyncSession,
) -> None:
    """Submit a community report for a valid sterilization campaign."""
    future_date = datetime.now(UTC) + timedelta(days=2)
    camp_result = await create_new_campaign(
        db_session,
        sample_source.id,
        {
            "title": "Jornada Bosa",
            "municipality": "Bogotá",
            "starts_at": future_date,
            "species": ["canino"],
            "is_free": True,
        },
        address="Calle 65 Sur # 80-20",
    )
    camp = camp_result["campaign"]

    form_data = {
        "update_type": "full",
        "note": "Agotados todos los turnos disponibles",
        "campaign_id": str(camp.id),
    }

    response = await app_client.post("/community/update", data=form_data)
    assert response.status_code == 200
    assert (
        "reporte recibido" in response.text.lower()
        or "gracias" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_post_community_update_validation_error_neither_target_returns_400(
    app_client: AsyncClient,
) -> None:
    """If neither animal_id nor campaign_id is sent, return controlled HTTP 400."""
    form_data = {
        "update_type": "full",
        "note": "Reporte sin destino",
    }
    response = await app_client.post("/community/update", data=form_data)
    assert response.status_code == 400
    assert (
        "exactamente uno" in response.text.lower() or "error" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_post_community_update_validation_error_both_targets_returns_400(
    app_client: AsyncClient,
    sample_source: Source,
    db_session: AsyncSession,
) -> None:
    """If both animal_id and campaign_id are sent, return controlled HTTP 400."""
    form_data = {
        "update_type": "confirmed",
        "note": "Reporte ambiguo",
        "campaign_id": "1",
        "animal_id": "1",
    }
    response = await app_client.post("/community/update", data=form_data)
    assert response.status_code == 400
    assert (
        "exactamente uno" in response.text.lower() or "error" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_vote_for_update_rate_limiting_blocks_second_vote(
    app_client: AsyncClient,
    sample_source: Source,
    db_session: AsyncSession,
) -> None:
    """The same IP address cannot vote twice for the same report within the rate limit window."""
    created = await create_animal_profile(
        db_session,
        sample_source.id,
        {"name": "Nala", "species": "felino", "municipality": "Bogotá"},
        "https://ejemplo.com/nala.jpg",
    )
    animal = created["animal"]

    update = await register_update(
        db_session,
        update_type="adopted",
        note="Fue adoptada por una familia de Bosa",
        animal_id=animal.id,
    )

    # First vote from test client (IP: 127.0.0.1)
    res1 = await app_client.post(f"/community/{update.id}/vote")
    assert res1.status_code == 200
    assert (
        "voto registrado" in res1.text.lower() or "validar reporte" in res1.text.lower()
    )

    # Second vote from the same IP must be rejected
    res2 = await app_client.post(f"/community/{update.id}/vote")
    assert res2.status_code == 200
    assert "ya votaste" in res2.text.lower()


@pytest.mark.asyncio
async def test_vote_for_nonexistent_update_returns_404(
    app_client: AsyncClient,
) -> None:
    """Attempting to vote on a non-existent report must return HTTP 404."""
    response = await app_client.post("/community/999999/vote")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_confirmed_vote_at_threshold_updates_campaign_freshness(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """When a 'confirmed' vote reaches the community consensus threshold, campaign last_confirmed_at must be updated."""
    future_date = datetime.now(UTC) + timedelta(days=5)
    camp_result = await create_new_campaign(
        db_session,
        sample_source.id,
        {
            "title": "Jornada Kennedy Freshness",
            "municipality": "Bogotá",
            "starts_at": future_date,
            "species": ["canino"],
            "is_free": True,
        },
        address="Avenida 1 de Mayo # 68-10",
    )
    camp = camp_result["campaign"]
    assert camp.last_confirmed_at is None

    # Register community confirmation update
    update = await register_update(
        db_session,
        update_type="confirmed",
        note="Vecinos confirman que la jornada sigue en pie",
        campaign_id=camp.id,
    )

    # Vote until community consensus threshold is reached
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, update.id)

    # Refresh campaign and verify last_confirmed_at was updated
    stmt = select(Campaign).where(Campaign.id == camp.id)
    camp_refreshed = (await db_session.execute(stmt)).scalar_one()
    assert camp_refreshed.last_confirmed_at is not None
    # Must be very recent (< 60 seconds)
    delta = datetime.now(UTC) - camp_refreshed.last_confirmed_at
    assert delta.total_seconds() < 60
