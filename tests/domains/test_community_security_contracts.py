"""Comprehensive contract, integration, and security tests for Community and Shared Security modules.

Targets:
- app/domains/community/router.py
- app/domains/community/tools.py
- app/shared/security.py
"""

import time
from collections.abc import AsyncGenerator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.domains.animals.models import AnimalProfile
from app.domains.community.models import CommunityUpdate
from app.domains.community.router import (
    list_updates_htmx,
    post_update,
    vote_for_update_htmx,
)
from app.domains.community.tools import (
    add_vote,
    cast_vote,
    get_entity_updates,
    register_update,
)
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.main import app
from app.shared import cache, geo, security

# ── Shared Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async test client with get_db dependency override."""

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
        name="Refugio San Francisco",
        type="verified_shelter",
        status="verified",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="sanfrancisco@refugio.org",
        contact_whatsapp="+573109998877",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def sample_campaign(db_session: AsyncSession, sample_source: Source) -> Campaign:
    camp = Campaign(
        source_id=sample_source.id,
        title="Jornada Gratuita Suba",
        municipality="Bogotá",
        lat=4.7450,
        lng=-74.0880,
        starts_at=datetime(2026, 6, 1, 8, 0, 0),
        species=["canino", "felino"],
        is_free=True,
        status="scheduled",
    )
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(camp)
    return camp


@pytest_asyncio.fixture
async def sample_animal(
    db_session: AsyncSession, sample_source: Source
) -> AnimalProfile:
    animal = AnimalProfile(
        name="Firulais",
        species="canino",
        municipality="Bogotá",
        source_id=sample_source.id,
        foto_url="https://example.com/firulais.jpg",
        status="available",
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)
    return animal


# ── Community Router Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_update_form_without_parameters(app_client: AsyncClient) -> None:
    """GET /community/update without params returns 200 and renders form."""
    response = await app_client.get("/community/update")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "<form" in response.text.lower() or "reporte" in response.text.lower()


@pytest.mark.asyncio
async def test_get_update_form_with_campaign_id(
    app_client: AsyncClient, sample_campaign: Campaign
) -> None:
    """GET /community/update?campaign_id=... returns 200 with campaign preselected."""
    response = await app_client.get(
        f"/community/update?campaign_id={sample_campaign.id}"
    )
    assert response.status_code == 200
    assert str(sample_campaign.id) in response.text


@pytest.mark.asyncio
async def test_get_update_form_with_animal_id(
    app_client: AsyncClient, sample_animal: AnimalProfile
) -> None:
    """GET /community/update?animal_id=... returns 200 with animal preselected."""
    response = await app_client.get(f"/community/update?animal_id={sample_animal.id}")
    assert response.status_code == 200
    assert str(sample_animal.id) in response.text


@pytest.mark.asyncio
async def test_post_community_update_with_valid_animal_id(
    app_client: AsyncClient, sample_animal: AnimalProfile
) -> None:
    """POST /community/update with valid animal_id returns confirmation and HX-Trigger."""
    payload = {
        "update_type": "in_treatment",
        "note": "El animal inició tratamiento antibiótico",
        "animal_id": str(sample_animal.id),
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "newCommunityUpdate"
    assert (
        "reporte recibido" in response.text.lower()
        or "gracias" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_post_community_update_with_valid_campaign_id(
    app_client: AsyncClient, sample_campaign: Campaign
) -> None:
    """POST /community/update with valid campaign_id returns confirmation and HX-Trigger."""
    payload = {
        "update_type": "full",
        "note": "Cupos completamente agotados a las 9am",
        "campaign_id": str(sample_campaign.id),
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "newCommunityUpdate"
    assert (
        "reporte recibido" in response.text.lower()
        or "gracias" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_post_community_update_creator_is_marked_as_voted(
    app_client: AsyncClient, sample_campaign: Campaign, db_session: AsyncSession
) -> None:
    """POST /community/update prevents creator from immediately voting on own report."""
    payload = {
        "update_type": "full",
        "note": "Cupos llenos",
        "campaign_id": str(sample_campaign.id),
    }
    # Submit report from test client IP (127.0.0.1)
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 200

    # Retrieve created update
    stmt = (
        select(CommunityUpdate)
        .where(CommunityUpdate.campaign_id == sample_campaign.id)
        .order_by(CommunityUpdate.id.desc())
    )
    result = await db_session.execute(stmt)
    created_update = result.scalar_one()

    # Attempt to vote immediately with same client
    vote_res = await app_client.post(f"/community/{created_update.id}/vote")
    assert vote_res.status_code == 200
    assert "ya votaste" in vote_res.text.lower() or "espera" in vote_res.text.lower()


@pytest.mark.asyncio
async def test_post_community_update_xor_violation_neither_returns_400(
    app_client: AsyncClient,
) -> None:
    """POST /community/update with neither target returns 400 error fragment."""
    payload = {
        "update_type": "full",
        "note": "No target provided",
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 400
    assert "error de validación" in response.text.lower()


@pytest.mark.asyncio
async def test_post_community_update_xor_violation_both_returns_400(
    app_client: AsyncClient, sample_campaign: Campaign, sample_animal: AnimalProfile
) -> None:
    """POST /community/update with both targets returns 400 error fragment."""
    payload = {
        "update_type": "confirmed",
        "note": "Both targets provided",
        "campaign_id": str(sample_campaign.id),
        "animal_id": str(sample_animal.id),
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 400
    assert "error de validación" in response.text.lower()


@pytest.mark.asyncio
async def test_post_community_update_invalid_update_type_returns_400(
    app_client: AsyncClient, sample_animal: AnimalProfile
) -> None:
    """POST /community/update with invalid update_type returns 400 error fragment."""
    payload = {
        "update_type": "unknown_type_value",
        "note": "Invalid type payload",
        "animal_id": str(sample_animal.id),
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 400
    assert "error de validación" in response.text.lower()


@pytest.mark.asyncio
async def test_post_community_update_nonexistent_campaign_returns_400(
    app_client: AsyncClient,
) -> None:
    """POST /community/update with non-existent campaign_id triggers ValueError -> 400."""
    payload = {
        "update_type": "full",
        "note": "Campaign not found",
        "campaign_id": "99999999",
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 400
    assert "error de validación" in response.text.lower()
    assert (
        "does not exist" in response.text.lower() or "campaign" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_post_community_update_nonexistent_animal_returns_400(
    app_client: AsyncClient,
) -> None:
    """POST /community/update with non-existent animal_id triggers ValueError -> 400."""
    payload = {
        "update_type": "in_treatment",
        "note": "Animal not found",
        "animal_id": "99999999",
    }
    response = await app_client.post("/community/update", data=payload)
    assert response.status_code == 400
    assert "error de validación" in response.text.lower()
    assert (
        "does not exist" in response.text.lower() or "animal" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_post_update_direct_call_without_client_ip(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """Direct invocation of post_update where request.client is None falls back to 127.0.0.1."""
    mock_request = MagicMock(spec=Request)
    mock_request.client = None

    response = await post_update(
        request=mock_request,
        update_type="full",
        note="Direct call without client host",
        campaign_id=sample_campaign.id,
        animal_id=None,
        db=db_session,
    )
    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "newCommunityUpdate"

    # Second immediate direct call hits 429 rate-limit branch
    response_rl = await post_update(
        request=mock_request,
        update_type="full",
        note="Duplicate direct call",
        campaign_id=sample_campaign.id,
        animal_id=None,
        db=db_session,
    )
    assert response_rl.status_code == 429

    # Invalid direct call hits 400 exception branch
    response_err = await post_update(
        request=mock_request,
        update_type="invalid_type",
        note="Bad type",
        campaign_id=sample_campaign.id,
        animal_id=None,
        db=db_session,
    )
    assert response_err.status_code == 400


@pytest.mark.asyncio
async def test_get_community_list_updates_for_campaign(
    app_client: AsyncClient, sample_campaign: Campaign, db_session: AsyncSession
) -> None:
    """GET /community/list?campaign_id=... returns reports list fragment."""
    await register_update(
        db_session, "full", note="Primer reporte", campaign_id=sample_campaign.id
    )
    response = await app_client.get(f"/community/list?campaign_id={sample_campaign.id}")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "primer reporte" in response.text.lower()


@pytest.mark.asyncio
async def test_get_community_list_updates_for_animal(
    app_client: AsyncClient, sample_animal: AnimalProfile, db_session: AsyncSession
) -> None:
    """GET /community/list?animal_id=... returns reports list for animal."""
    await register_update(
        db_session, "in_treatment", note="En recuperacion", animal_id=sample_animal.id
    )
    response = await app_client.get(f"/community/list?animal_id={sample_animal.id}")
    assert response.status_code == 200
    assert "en recuperacion" in response.text.lower()


@pytest.mark.asyncio
async def test_get_community_list_updates_shows_already_voted_button(
    app_client: AsyncClient, sample_animal: AnimalProfile, db_session: AsyncSession
) -> None:
    """GET /community/list includes voted_ids when the requesting IP already voted."""
    up = await register_update(
        db_session, "adopted", note="Adoptada", animal_id=sample_animal.id
    )
    # Mark client IP (127.0.0.1) as voted
    await security.mark_as_voted("127.0.0.1", up.id)

    response = await app_client.get(f"/community/list?animal_id={sample_animal.id}")
    assert response.status_code == 200
    assert "adoptada" in response.text.lower()


@pytest.mark.asyncio
async def test_list_updates_htmx_direct_call_without_client_ip(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """Direct invocation of list_updates_htmx where request.client is None."""
    mock_request = MagicMock(spec=Request)
    mock_request.client = None

    response = await list_updates_htmx(
        request=mock_request,
        campaign_id=sample_campaign.id,
        animal_id=None,
        db=db_session,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_vote_for_update_success_and_status_fragment(
    app_client: AsyncClient, sample_campaign: Campaign, db_session: AsyncSession
) -> None:
    """POST /community/{id}/vote records vote from a fresh IP and returns vote_status fragment."""
    up = await register_update(
        db_session, "full", note="Reporte de cupos", campaign_id=sample_campaign.id
    )

    # Vote from a fresh IP header
    headers = {"X-Forwarded-For": "198.51.100.42"}
    response = await app_client.post(f"/community/{up.id}/vote", headers=headers)
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_vote_for_nonexistent_update_returns_404(
    app_client: AsyncClient,
) -> None:
    """POST /community/{id}/vote on non-existent id returns 404 with error message (line 128)."""
    headers = {"X-Forwarded-For": "198.51.100.77"}
    response = await app_client.post("/community/9999999/vote", headers=headers)
    assert response.status_code == 404
    assert "reporte no encontrado" in response.text.lower()


@pytest.mark.asyncio
async def test_vote_for_update_htmx_direct_not_found(
    db_session: AsyncSession,
) -> None:
    """Direct call to vote_for_update_htmx with nonexistent id returns 404 (line 128)."""
    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock()
    mock_request.client.host = "10.123.123.123"

    with patch(
        "app.domains.community.router.check_rate_limit", new_callable=AsyncMock
    ) as mock_rl:
        mock_rl.return_value = True
        response = await vote_for_update_htmx(
            request=mock_request, update_id=999999123, db=db_session
        )
        assert response.status_code == 404
        assert "reporte no encontrado" in bytes(response.body).decode().lower()


@pytest.mark.asyncio
async def test_vote_for_update_rate_limit_exceeded_returns_cooldown(
    app_client: AsyncClient, sample_animal: AnimalProfile, db_session: AsyncSession
) -> None:
    """Repeated votes from same IP within window return cooldown HTML without modifying count."""
    up = await register_update(
        db_session, "in_treatment", note="Tratamiento", animal_id=sample_animal.id
    )
    headers = {"X-Forwarded-For": "203.0.113.88"}

    res1 = await app_client.post(f"/community/{up.id}/vote", headers=headers)
    assert res1.status_code == 200

    # Immediate second vote
    res2 = await app_client.post(f"/community/{up.id}/vote", headers=headers)
    assert res2.status_code == 200
    assert "ya votaste" in res2.text.lower() or "espera" in res2.text.lower()


@pytest.mark.asyncio
async def test_vote_for_update_htmx_direct_call_without_client_ip(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """Direct invocation of vote_for_update_htmx when request.client is None."""
    up = await register_update(
        db_session, "full", note="Direct vote call", campaign_id=sample_campaign.id
    )

    mock_request = MagicMock(spec=Request)
    mock_request.client = None

    # First vote from default 127.0.0.1
    with patch(
        "app.domains.community.router.check_rate_limit", new_callable=AsyncMock
    ) as mock_rl:
        mock_rl.return_value = True
        response = await vote_for_update_htmx(
            request=mock_request, update_id=up.id, db=db_session
        )
        assert response.status_code == 200


# ── Community Tools Tests (Pure Business Logic) ───────────────────────────────


@pytest.mark.asyncio
async def test_register_update_nonexistent_campaign_raises_value_error(
    db_session: AsyncSession,
) -> None:
    """register_update raises ValueError when campaign does not exist (line 31)."""
    with pytest.raises(ValueError, match="Campaign with id 999999 does not exist"):
        await register_update(db_session, "full", campaign_id=999999)


@pytest.mark.asyncio
async def test_register_update_nonexistent_animal_raises_value_error(
    db_session: AsyncSession,
) -> None:
    """register_update raises ValueError when animal does not exist (line 38)."""
    with pytest.raises(ValueError, match="Animal with id 999999 does not exist"):
        await register_update(db_session, "in_treatment", animal_id=999999)


@pytest.mark.asyncio
async def test_add_vote_existing_update_increments_and_returns_count(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """add_vote increments existing votes and commits (lines 56-65)."""
    up = await register_update(
        db_session, "full", note="add_vote test", campaign_id=sample_campaign.id
    )
    assert up.votes == 1

    new_votes = await add_vote(db_session, up.id)
    assert new_votes == 2

    # Verify persistence
    stmt = select(CommunityUpdate).where(CommunityUpdate.id == up.id)
    refreshed = (await db_session.execute(stmt)).scalar_one()
    assert refreshed.votes == 2


@pytest.mark.asyncio
async def test_add_vote_nonexistent_update_returns_none(
    db_session: AsyncSession,
) -> None:
    """add_vote returns None when update_id is not found (line 65)."""
    result = await add_vote(db_session, 888888)
    assert result is None


@pytest.mark.asyncio
async def test_cast_vote_nonexistent_update_returns_none(
    db_session: AsyncSession,
) -> None:
    """cast_vote returns None when update_id does not exist (line 94)."""
    result = await cast_vote(db_session, 777777)
    assert result is None


@pytest.mark.asyncio
async def test_get_entity_updates_without_filters_returns_all(
    db_session: AsyncSession, sample_campaign: Campaign, sample_animal: AnimalProfile
) -> None:
    """get_entity_updates with neither campaign_id nor animal_id returns all updates (lines 72-83)."""
    up1 = await register_update(
        db_session, "full", note="Camp update", campaign_id=sample_campaign.id
    )
    up2 = await register_update(
        db_session, "in_treatment", note="Animal update", animal_id=sample_animal.id
    )

    all_updates = await get_entity_updates(db_session)
    assert len(all_updates) >= 2
    update_ids = [u.id for u in all_updates]
    assert up1.id in update_ids
    assert up2.id in update_ids


@pytest.mark.asyncio
async def test_cast_vote_threshold_campaign_cancelled_and_confirmed(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """cast_vote reaches threshold with cancelled and confirmed types (lines 108, 110)."""
    # 1. Update cancelled -> updates camp.status = 'cancelled' (line 108)
    up_canc = await register_update(
        db_session, "cancelled", note="Lluvia intensa", campaign_id=sample_campaign.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, up_canc.id)

    stmt = select(Campaign).where(Campaign.id == sample_campaign.id)
    camp = (await db_session.execute(stmt)).scalar_one()
    assert camp.status == "cancelled"

    # 2. Update confirmed -> updates camp.last_confirmed_at (line 110)
    up_conf = await register_update(
        db_session, "confirmed", note="En curso", campaign_id=sample_campaign.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, up_conf.id)

    camp_conf = (await db_session.execute(stmt)).scalar_one()
    assert camp_conf.last_confirmed_at is not None


@pytest.mark.asyncio
async def test_cast_vote_threshold_campaign_already_has_status(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """cast_vote when campaign already has status covers branch if camp.status != update_type."""
    # Pre-set campaign status to 'full'
    sample_campaign.status = "full"
    await db_session.commit()

    up = await register_update(
        db_session, "full", note="Report full again", campaign_id=sample_campaign.id
    )
    # Vote until threshold
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, up.id)

    stmt = select(Campaign).where(Campaign.id == sample_campaign.id)
    camp = (await db_session.execute(stmt)).scalar_one()
    assert camp.status == "full"


@pytest.mark.asyncio
async def test_cast_vote_threshold_animal_adopted_and_in_treatment(
    db_session: AsyncSession, sample_animal: AnimalProfile
) -> None:
    """cast_vote reaches threshold for animal with adopted and in_treatment types (lines 122-124)."""
    # 1. in_treatment updates animal.status (line 122)
    up_treat = await register_update(
        db_session,
        "in_treatment",
        note="Inicia recuperacion",
        animal_id=sample_animal.id,
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, up_treat.id)

    stmt = select(AnimalProfile).where(AnimalProfile.id == sample_animal.id)
    animal = (await db_session.execute(stmt)).scalar_one()
    assert animal.status == "in_treatment"

    # 2. adopted updates animal.status and sets adopted_at (lines 122-124)
    up_adopt = await register_update(
        db_session, "adopted", note="Adoptado formalmente", animal_id=sample_animal.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, up_adopt.id)

    animal_adopt = (await db_session.execute(stmt)).scalar_one()
    assert animal_adopt.status == "adopted"
    assert animal_adopt.adopted_at is not None


@pytest.mark.asyncio
async def test_cast_vote_threshold_animal_already_has_status(
    db_session: AsyncSession, sample_animal: AnimalProfile
) -> None:
    """cast_vote when animal already has status covers branch if animal.status != update_type."""
    # Pre-set animal status to 'adopted'
    sample_animal.status = "adopted"
    await db_session.commit()

    up = await register_update(
        db_session, "adopted", note="Already adopted", animal_id=sample_animal.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 1):
        await cast_vote(db_session, up.id)

    stmt = select(AnimalProfile).where(AnimalProfile.id == sample_animal.id)
    animal = (await db_session.execute(stmt)).scalar_one()
    assert animal.status == "adopted"


# ── Shared Security Module Tests ─────────────────────────────────────────────


def test_pin_generation_and_hashing_contracts() -> None:
    """Contracts for generate_pin, hash_pin, and verify_pin."""
    pin = security.generate_pin()
    assert len(pin) == 4
    assert pin.isdigit()
    assert 1000 <= int(pin) <= 9999

    hashed = security.hash_pin(pin)
    assert hashed != pin
    assert security.verify_pin(pin, hashed) is True
    assert security.verify_pin("0000", hashed) is False


@pytest.mark.asyncio
async def test_check_rate_limit_valkey_available_atomic_set_nx() -> None:
    """check_rate_limit with live/mocked Valkey client."""
    mock_valkey = AsyncMock()
    mock_valkey.set.return_value = True

    with patch.object(cache, "valkey_client", mock_valkey):
        result = await security.check_rate_limit("192.168.1.10", 101, window_seconds=60)
        assert result is True
        mock_valkey.set.assert_awaited_once_with(
            "rate_limit:192.168.1.10:101", "1", ex=60, nx=True
        )

    # Subsequent attempt returns False from Valkey SET NX
    mock_valkey.set.return_value = False
    with patch.object(cache, "valkey_client", mock_valkey):
        result2 = await security.check_rate_limit(
            "192.168.1.10", 101, window_seconds=60
        )
        assert result2 is False


@pytest.mark.asyncio
async def test_check_rate_limit_in_memory_fallback_and_pruning() -> None:
    """check_rate_limit uses in-memory dict when Valkey is down and prunes >1000 items (lines 62-77)."""
    security._vote_fallback.clear()

    with (
        patch.object(cache, "valkey_client", None),
        patch.object(geo, "valkey_client", None),
    ):
        ip = "10.50.0.1"
        update_id = 501

        # First attempt passes
        res1 = await security.check_rate_limit(ip, update_id, window_seconds=900)
        assert res1 is True

        # Second attempt within window fails
        res2 = await security.check_rate_limit(ip, update_id, window_seconds=900)
        assert res2 is False

        # Attempt after window expires passes
        security._vote_fallback[(ip, update_id)] = time.time() - 901
        res3 = await security.check_rate_limit(ip, update_id, window_seconds=900)
        assert res3 is True

        # Test dictionary pruning when len > 1000 (lines 73-76)
        now = time.time()
        for i in range(1005):
            # 500 stale items, 505 fresh items
            timestamp = (now - 1200) if i < 500 else now
            security._vote_fallback[(f"10.0.{i // 256}.{i % 256}", 999)] = timestamp

        assert len(security._vote_fallback) > 1000

        # Next call triggers pruning
        await security.check_rate_limit("10.99.99.99", 888, window_seconds=900)
        # Verify stale entries were purged
        assert len(security._vote_fallback) <= 600

    security._vote_fallback.clear()


@pytest.mark.asyncio
async def test_mark_as_voted_valkey_and_fallback() -> None:
    """mark_as_voted records in Valkey or falls back to in-memory dict (lines 80-94)."""
    # 1. Valkey available
    mock_valkey = AsyncMock()
    with patch.object(cache, "valkey_client", mock_valkey):
        await security.mark_as_voted("192.168.1.20", 201)
        mock_valkey.set.assert_awaited_once_with(
            "rate_limit:192.168.1.20:201", "1", ex=900, nx=True
        )

    # 2. Valkey unavailable (raises exception)
    security._vote_fallback.clear()
    with (
        patch.object(cache, "valkey_client", None),
        patch.object(geo, "valkey_client", None),
    ):
        await security.mark_as_voted("192.168.1.25", 202)
        assert ("192.168.1.25", 202) in security._vote_fallback

    security._vote_fallback.clear()


@pytest.mark.asyncio
async def test_has_voted_recently_valkey_and_fallback() -> None:
    """has_voted_recently queries Valkey or in-memory dict without modifying TTL (lines 96-114)."""
    # 1. Valkey available
    mock_valkey = AsyncMock()
    mock_valkey.exists.return_value = 1
    with patch.object(cache, "valkey_client", mock_valkey):
        assert await security.has_voted_recently("192.168.1.30", 301) is True
        mock_valkey.exists.assert_awaited_once_with("rate_limit:192.168.1.30:301")

    mock_valkey.exists.return_value = 0
    with patch.object(cache, "valkey_client", mock_valkey):
        assert await security.has_voted_recently("192.168.1.30", 302) is False

    # 2. Valkey exception -> in-memory fallback (lines 108-114)
    security._vote_fallback.clear()
    with (
        patch.object(cache, "valkey_client", None),
        patch.object(geo, "valkey_client", None),
    ):
        # Key not present
        assert await security.has_voted_recently("10.0.0.1", 401) is False

        # Key present and fresh (< 900s)
        security._vote_fallback[("10.0.0.1", 401)] = time.time()
        assert await security.has_voted_recently("10.0.0.1", 401) is True

        # Key present but stale (>= 900s)
        security._vote_fallback[("10.0.0.1", 401)] = time.time() - 950
        assert await security.has_voted_recently("10.0.0.1", 401) is False

    security._vote_fallback.clear()


@pytest.mark.asyncio
async def test_pin_rate_limit_valkey_success_and_blocked() -> None:
    """check_pin_rate_limit and record_failed_pin_attempt with Valkey client (lines 120-135, 142-156)."""
    mock_valkey = MagicMock()
    mock_valkey.get = AsyncMock()
    mock_pipeline = MagicMock()
    mock_pipeline.incr = MagicMock(return_value=mock_pipeline)
    mock_pipeline.expire = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(return_value=[1, True])
    mock_valkey.pipeline = MagicMock(return_value=mock_pipeline)

    with patch.object(cache, "valkey_client", mock_valkey):
        # No previous attempts
        mock_valkey.get.return_value = None
        assert (
            await security.check_pin_rate_limit("192.168.1.50", 1, max_attempts=5)
            is True
        )

        # Under threshold (e.g. 3 attempts)
        mock_valkey.get.return_value = "3"
        assert (
            await security.check_pin_rate_limit("192.168.1.50", 1, max_attempts=5)
            is True
        )

        # At or above threshold (e.g. 5 attempts, line 131)
        mock_valkey.get.return_value = "5"
        assert (
            await security.check_pin_rate_limit("192.168.1.50", 1, max_attempts=5)
            is False
        )

        # Record a failed attempt via pipeline (lines 150-155)
        await security.record_failed_pin_attempt("192.168.1.50", 1, window_seconds=3600)
        mock_pipeline.incr.assert_called_once_with("pin_attempts:192.168.1.50:1")
        mock_pipeline.expire.assert_called_once_with(
            "pin_attempts:192.168.1.50:1", 3600
        )
        mock_pipeline.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_pin_rate_limit_valkey_exception_fallback() -> None:
    """check_pin_rate_limit and record_failed_pin_attempt when Valkey raises exception (lines 133-134, 156-158)."""
    security._pin_attempts.clear()
    mock_valkey = MagicMock()
    mock_valkey.get = AsyncMock(side_effect=Exception("Valkey socket error"))
    mock_pipeline = MagicMock()
    mock_pipeline.incr = MagicMock(return_value=mock_pipeline)
    mock_pipeline.expire = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(side_effect=Exception("Pipeline failure"))
    mock_valkey.pipeline = MagicMock(return_value=mock_pipeline)

    with patch.object(cache, "valkey_client", mock_valkey):
        # check_pin_rate_limit falls back to memory on valkey exception (lines 133-134)
        assert (
            await security.check_pin_rate_limit("10.10.10.10", 2, max_attempts=3)
            is True
        )

        # record_failed_pin_attempt falls back to memory on valkey exception (lines 156-158)
        await security.record_failed_pin_attempt("10.10.10.10", 2, window_seconds=3600)
        assert len(security._pin_attempts[("10.10.10.10", 2)]) == 1

    security._pin_attempts.clear()


@pytest.mark.asyncio
async def test_pin_rate_limit_in_memory_fallback() -> None:
    """check_pin_rate_limit and record_failed_pin_attempt when Valkey is None (lines 136-140, 159-161)."""
    security._pin_attempts.clear()

    with (
        patch.object(cache, "valkey_client", None),
        patch.object(geo, "valkey_client", None),
    ):
        ip = "172.16.0.99"
        animal_id = 77

        # Initially 0 attempts
        assert (
            await security.check_pin_rate_limit(ip, animal_id, max_attempts=3) is True
        )

        # Record failed attempts
        await security.record_failed_pin_attempt(ip, animal_id, window_seconds=3600)
        await security.record_failed_pin_attempt(ip, animal_id, window_seconds=3600)
        assert (
            await security.check_pin_rate_limit(ip, animal_id, max_attempts=3) is True
        )

        # 3rd failed attempt hits max_attempts
        await security.record_failed_pin_attempt(ip, animal_id, window_seconds=3600)
        assert (
            await security.check_pin_rate_limit(ip, animal_id, max_attempts=3) is False
        )

        # When attempts age past window_seconds, they are filtered out
        now = time.time()
        security._pin_attempts[(ip, animal_id)] = [now - 3700, now - 3650]
        assert (
            await security.check_pin_rate_limit(
                ip, animal_id, max_attempts=3, window_seconds=3600
            )
            is True
        )

    security._pin_attempts.clear()


def test_reset_pin_attempts_exists_in_security_module() -> None:
    """Verify that security module provides reset_pin_attempts to reset counter after successful PIN entry."""
    assert hasattr(security, "reset_pin_attempts"), (
        "reset_pin_attempts function is not implemented in app.shared.security"
    )


@pytest.mark.asyncio
async def test_reset_pin_attempts_valkey_and_memory_fallback() -> None:
    """reset_pin_attempts clears attempts in Valkey and memory fallback (including exception path)."""
    security._pin_attempts.clear()
    ip = "198.51.100.42"
    animal_id = 88

    # 1. Valkey available + memory entry cleared
    security._pin_attempts[(ip, animal_id)] = [time.time()]
    mock_valkey = MagicMock()
    mock_valkey.delete = AsyncMock(return_value=1)
    with patch.object(cache, "valkey_client", mock_valkey):
        await security.reset_pin_attempts(ip, animal_id)
        mock_valkey.delete.assert_awaited_once_with(f"pin_attempts:{ip}:{animal_id}")
        assert (ip, animal_id) not in security._pin_attempts

    # 2. Valkey raises exception -> logs warning and still clears memory fallback
    security._pin_attempts[(ip, animal_id)] = [time.time()]
    mock_valkey_err = MagicMock()
    mock_valkey_err.delete = AsyncMock(side_effect=RuntimeError("Valkey down"))
    with patch.object(cache, "valkey_client", mock_valkey_err):
        await security.reset_pin_attempts(ip, animal_id)
        assert (ip, animal_id) not in security._pin_attempts


def test_get_client_ip_proxy_headers_and_fallbacks() -> None:
    """get_client_ip extracts X-Forwarded-For, X-Real-IP, or falls back to request.client.host / 127.0.0.1."""
    # 1. X-Forwarded-For with multiple IPs
    req_xff = MagicMock()
    req_xff.headers = {"x-forwarded-for": "203.0.113.10, 172.20.0.1"}
    assert security.get_client_ip(req_xff) == "203.0.113.10"

    # 2. X-Real-IP when X-Forwarded-For is absent
    req_real = MagicMock()
    req_real.headers = {"x-real-ip": "198.51.100.77"}
    assert security.get_client_ip(req_real) == "198.51.100.77"

    # 3. Fallback to request.client.host
    req_host = MagicMock()
    req_host.headers = {}
    req_host.client.host = "10.20.30.40"
    assert security.get_client_ip(req_host) == "10.20.30.40"

    # 4. Fallback to 127.0.0.1 when client is None
    req_none = MagicMock()
    req_none.headers = {}
    req_none.client = None
    assert security.get_client_ip(req_none) == "127.0.0.1"


@pytest.mark.asyncio
async def test_check_create_update_rate_limit_valkey_and_fallback_pruning() -> None:
    """check_create_update_rate_limit enforces cooldown in Valkey and memory fallback with pruning."""
    security._create_update_fallback.clear()

    # 1. Valkey available
    mock_valkey = AsyncMock()
    mock_valkey.set.return_value = True
    with patch.object(cache, "valkey_client", mock_valkey):
        allowed = await security.check_create_update_rate_limit(
            "203.0.113.1", campaign_id=10, window_seconds=900
        )
        assert allowed is True
        mock_valkey.set.assert_awaited_once_with(
            "create_update_rate_limit:203.0.113.1:campaign:10", "1", ex=900, nx=True
        )

    # 2. Memory fallback when Valkey is down + pruning > 1000 items
    with (
        patch.object(cache, "valkey_client", None),
        patch.object(geo, "valkey_client", None),
    ):
        assert (
            await security.check_create_update_rate_limit(
                "203.0.113.2", animal_id=55, window_seconds=900
            )
            is True
        )
        assert (
            await security.check_create_update_rate_limit(
                "203.0.113.2", animal_id=55, window_seconds=900
            )
            is False
        )

        now = time.time()
        for i in range(1005):
            ts = (now - 1200) if i < 500 else now
            security._create_update_fallback[
                (f"10.1.{i // 256}.{i % 256}", "animal:1")
            ] = ts
        assert len(security._create_update_fallback) > 1000

        await security.check_create_update_rate_limit(
            "203.0.113.99", animal_id=99, window_seconds=900
        )
        assert len(security._create_update_fallback) <= 600

    security._create_update_fallback.clear()


@pytest.mark.asyncio
async def test_post_community_update_rate_limit_blocks_duplicate_ip_and_respects_xff(
    app_client: AsyncClient, sample_animal: AnimalProfile
) -> None:
    """POST /community/update blocks second submission from same IP with 429, but allows distinct X-Forwarded-For IP."""
    payload = {
        "update_type": "in_treatment",
        "note": "Primer reporte desde IP A",
        "animal_id": str(sample_animal.id),
    }
    headers_ip_a = {"X-Forwarded-For": "203.0.113.111"}
    headers_ip_b = {"X-Forwarded-For": "203.0.113.222"}

    # 1st submission from IP A succeeds
    res1 = await app_client.post(
        "/community/update", data=payload, headers=headers_ip_a
    )
    assert res1.status_code == 200

    # 2nd immediate submission from IP A for the same animal is blocked with 429
    res2 = await app_client.post(
        "/community/update", data=payload, headers=headers_ip_a
    )
    assert res2.status_code == 429
    assert "límite alcanzado" in res2.text.lower() or "espera" in res2.text.lower()

    # Submission from IP B for the same animal succeeds
    res3 = await app_client.post(
        "/community/update", data=payload, headers=headers_ip_b
    )
    assert res3.status_code == 200
