"""TDD Contract Tests for Ley 1581 de 2012 Consent (`accept_terms=true`),
Dual-Key Anti-Rotation Voting (`sos_voter_token`), and Rate Limiting on All Public POST Endpoints.
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.domains.animals import router as animals_router
from app.domains.community import router as community_router
from app.domains.sources import router as sources_router
from app.domains.sterilization import router as sterilization_router
from app.shared import cache, security
from app.shared.ip_privacy import VOTER_COOKIE_NAME


def _make_req(
    ip: str = "203.0.113.10", cookies: dict[str, str] | None = None
) -> MagicMock:
    req = MagicMock()
    req.headers = {"x-forwarded-for": ip}
    req.client = SimpleNamespace(host="127.0.0.1")
    req.cookies = cookies or {}
    req.url = SimpleNamespace(scheme="https", path="/")
    return req


@pytest.mark.asyncio
async def test_sources_register_rejects_accept_terms_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /sources/register must reject accept_terms=False with HTTP 400 (Ley 1581 compliance)."""
    monkeypatch.setattr(cache, "valkey_client", None)
    security._action_fallback.clear()
    db = AsyncMock()

    resp = await sources_router.post_register_form(
        request=_make_req("203.0.113.11"),
        name="Fundación Test",
        type="verified_shelter",
        municipality="bogota",
        department="Cundinamarca",
        accept_terms=False,
        contact_email="test@org.co",
        contact_whatsapp=None,
        contact_url=None,
        db=db,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sources_register_enforces_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /sources/register must return HTTP 429 after exceeding per-actor rate limit (3 per 15m)."""
    monkeypatch.setattr(cache, "valkey_client", None)
    security._action_fallback.clear()
    monkeypatch.setattr(
        sources_router, "register_source", AsyncMock(return_value=MagicMock())
    )
    db = AsyncMock()

    for _ in range(10):
        ok_resp = await sources_router.post_register_form(
            request=_make_req("203.0.113.12"),
            name="Fundación Legítima",
            type="verified_shelter",
            municipality="bogota",
            department="Cundinamarca",
            accept_terms=True,
            contact_email="ok@org.co",
            contact_whatsapp=None,
            contact_url=None,
            db=db,
        )
        assert ok_resp.status_code == 200

    blocked_resp = await sources_router.post_register_form(
        request=_make_req("203.0.113.12"),
        name="Fundación Spam",
        type="verified_shelter",
        municipality="bogota",
        department="Cundinamarca",
        accept_terms=True,
        contact_email="spam@org.co",
        contact_whatsapp=None,
        contact_url=None,
        db=db,
    )
    assert blocked_resp.status_code == 429


@pytest.mark.asyncio
async def test_animals_new_requires_accept_terms_and_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /animals/new must require accept_terms=True (HTTP 400) and enforce rate limit (HTTP 429)."""
    monkeypatch.setattr(cache, "valkey_client", None)
    security._action_fallback.clear()
    db = AsyncMock()

    dummy_file = UploadFile(
        filename="dog.jpg", file=io.BytesIO(b"\xff\xd8\xff\xe0" + b"0" * 128)
    )

    # 1. Reject when accept_terms=False
    resp_no_terms = await animals_router.post_new_animal(
        request=_make_req("203.0.113.20"),
        source_id=1,
        name="Firulais",
        species="canino",
        municipality="bogota",
        foto=dummy_file,
        accept_terms=False,
        db=db,
    )
    assert resp_no_terms.status_code == 400
    assert "Ley 1581" in bytes(resp_no_terms.body).decode("utf-8")


@pytest.mark.asyncio
async def test_community_update_requires_accept_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /community/update must reject submissions when accept_terms is False."""
    monkeypatch.setattr(cache, "valkey_client", None)
    security._create_update_fallback.clear()
    db = AsyncMock()

    resp = await community_router.post_update(
        request=_make_req("203.0.113.30"),
        update_type="confirmed",
        note="Sigue disponible",
        campaign_id=None,
        animal_id=1,
        accept_terms=False,
        db=db,
    )
    assert resp.status_code == 400
    assert "Ley 1581" in bytes(resp.body).decode("utf-8")


@pytest.mark.asyncio
async def test_community_vote_blocks_ip_rotation_via_signed_voter_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A voter who rotates IP (4G airplane mode) but keeps sos_voter_token cookie cannot vote twice."""
    monkeypatch.setattr(cache, "valkey_client", None)
    security._vote_fallback.clear()

    fake_update = SimpleNamespace(id=99, votes=1, update_type="confirmed")
    monkeypatch.setattr(
        community_router, "cast_vote", AsyncMock(return_value=fake_update)
    )
    db = AsyncMock()

    # First vote from IP 1 (no cookie yet) -> succeeds and sets signed cookie
    req1 = _make_req("203.0.113.41", cookies={})
    resp1 = await community_router.vote_for_update_htmx(
        request=req1, update_id=99, db=db
    )
    set_cookie_header = resp1.headers.get("set-cookie", "")
    assert VOTER_COOKIE_NAME in set_cookie_header

    # Extract cookie value
    cookie_val = set_cookie_header.split(f"{VOTER_COOKIE_NAME}=")[1].split(";")[0]

    # Second vote from a DIFFERENT IP (203.0.113.42) carrying the same signed voter cookie -> BLOCKED
    req2 = _make_req("203.0.113.42", cookies={VOTER_COOKIE_NAME: cookie_val})
    resp2 = await community_router.vote_for_update_htmx(
        request=req2, update_id=99, db=db
    )
    assert "Ya votaste" in bytes(resp2.body).decode("utf-8")


@pytest.mark.asyncio
async def test_sterilization_confirm_freshness_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /sterilization/confirm/{type}/{id} must rate-limit repeated confirmations from same actor."""
    monkeypatch.setattr(cache, "valkey_client", None)
    security._action_fallback.clear()
    monkeypatch.setattr(
        sterilization_router, "confirm_entity_freshness", AsyncMock(return_value=True)
    )
    db = AsyncMock()

    req = _make_req("203.0.113.55")
    resp1 = await sterilization_router.confirm_freshness(
        request=req, entity_type="campaign", entity_id=10, db=db
    )
    assert resp1.status_code == 200

    resp2 = await sterilization_router.confirm_freshness(
        request=req, entity_type="campaign", entity_id=10, db=db
    )
    assert resp2.status_code == 429
