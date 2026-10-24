"""Tests for sterilization domain tools and campaigns logic.

Covers:
- create_new_campaign: campaign creation with geocoding + PIN.
- create_new_fixed_point: creation of fixed veterinary point.
- find_nearby_campaigns: searches by municipality and species.
- get_campaign_detail: detail retrieval with source entity.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sources.models import Source
from app.domains.sterilization.tools import (
    create_new_campaign,
    create_new_fixed_point,
    find_nearby_campaigns,
    get_campaign_detail,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def sample_source(db_session: AsyncSession) -> Source:
    source = Source(
        name="Refugio Esteriliza Test",
        type="verified_shelter",
        status="verified",
        municipality="Medellín",
        department="Antioquia",
        contact_email="test@refugio.com",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


# ── TC-01: Create new campaign ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_new_campaign_returns_campaign_and_pin(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """create_new_campaign must return campaign entity, raw_pin, and contact_email."""
    data = {
        "title": "Jornada Test Centro",
        "municipality": "Medellín",
        "starts_at": datetime.now() + timedelta(days=7),
        "species": ["canino", "felino"],
        "is_free": True,
        "requirements": "Traer cobija",
    }
    result = await create_new_campaign(
        db_session, sample_source.id, data, "Calle 10 # 20-30"
    )

    assert "campaign" in result
    assert "raw_pin" in result
    assert "contact_email" in result
    assert result["campaign"].title == "Jornada Test Centro"
    assert result["campaign"].status == "scheduled"
    assert len(result["raw_pin"]) == 4
    assert result["raw_pin"].isdigit()
    assert result["contact_email"] == "test@refugio.com"


# ── TC-02: Create campaign with all optional fields ──────────────────────────


@pytest.mark.asyncio
async def test_create_new_campaign_with_optional_fields(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Optional fields such as booking_url and source_url are persisted."""
    data = {
        "title": "Jornada con Todo",
        "municipality": "Bogotá",
        "starts_at": datetime.now() + timedelta(days=14),
        "species": ["canino"],
        "is_free": False,
        "requirements": "Ayuno 8h",
        "booking_url": "https://forms.gle/test",
        "data_origin": "official_factual",
        "source_url": "https://datos.gov.co/jornada/1",
    }
    result = await create_new_campaign(
        db_session, sample_source.id, data, "Cra 7 # 50-60"
    )
    camp = result["campaign"]

    assert camp.booking_url == "https://forms.gle/test"
    assert not camp.is_free


# ── TC-03: Create fixed point ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_new_fixed_point(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """A fixed point is created with minimal required fields."""
    data = {
        "name": "Clínica Test",
        "address": "Calle 5 # 10-20",
        "municipality": "Medellín",
        "schedule_text": "Lunes a viernes 8am-5pm",
        "species": ["canino"],
        "is_free": True,
        "requirements": None,
    }
    fp = await create_new_fixed_point(db_session, sample_source.id, data)

    assert fp.id is not None
    assert fp.name == "Clínica Test"
    assert fp.schedule_text == "Lunes a viernes 8am-5pm"
    assert fp.data_origin == "source_submitted"


# ── TC-04: Fixed point with source_url ────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_new_fixed_point_with_source_url(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """source_url is properly saved on fixed points."""
    data = {
        "name": "Veterinaria Data",
        "address": "Cra 20 # 30-40",
        "municipality": "Bogotá",
        "schedule_text": "Sábados 9am-12pm",
        "species": ["felino"],
        "is_free": False,
        "source_url": "https://ejemplo.com/vet",
    }
    fp = await create_new_fixed_point(db_session, sample_source.id, data)

    assert fp.source_url == "https://ejemplo.com/vet"
    assert fp.is_free is False


# ── TC-05: Find campaigns by municipality ────────────────────────────────────


@pytest.mark.asyncio
async def test_find_nearby_campaigns_by_municipality(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """find_nearby_campaigns filters campaigns by municipality."""
    # Create campaigns across distinct municipalities
    data_bog = {
        "title": "Jornada Bogotá",
        "municipality": "bogota",
        "starts_at": datetime.now() + timedelta(days=5),
        "species": ["canino"],
        "is_free": True,
    }
    data_med = {
        "title": "Jornada Medellín",
        "municipality": "medellin",
        "starts_at": datetime.now() + timedelta(days=5),
        "species": ["felino"],
        "is_free": True,
    }
    await create_new_campaign(db_session, sample_source.id, data_bog, "Cra 1 # 2-3")
    await create_new_campaign(db_session, sample_source.id, data_med, "Cra 4 # 5-6")

    # Search in Medellin
    results = await find_nearby_campaigns(db_session, "medellin")
    assert len(results) >= 1
    assert all("medellin" in c.municipality.lower() for c in results)


# ── TC-06: Find campaigns by species ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_nearby_campaigns_by_species(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Species filter returns only campaigns that include that species."""
    data = {
        "title": "Solo Felinos",
        "municipality": "bogota",
        "starts_at": datetime.now() + timedelta(days=3),
        "species": ["felino"],
        "is_free": True,
    }
    await create_new_campaign(db_session, sample_source.id, data, "Cra 10 # 20-30")

    results = await find_nearby_campaigns(db_session, "bogota", species="felino")
    assert all("felino" in c.species for c in results)


# ── TC-07: Find campaigns with no matches ────────────────────────────────────


@pytest.mark.asyncio
async def test_find_nearby_campaigns_no_results(
    db_session: AsyncSession,
) -> None:
    """Municipality without campaigns returns empty list."""
    results = await find_nearby_campaigns(db_session, "municipio-inexistente-xyz")
    assert results == []


# ── TC-08: Campaign detail for existing campaign ─────────────────────────────


@pytest.mark.asyncio
async def test_get_campaign_detail_returns_campaign_and_source(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """get_campaign_detail returns campaign entity and its associated source."""
    data = {
        "title": "Jornada Detalle",
        "municipality": "cali",
        "starts_at": datetime.now() + timedelta(days=10),
        "species": ["canino", "felino"],
        "is_free": True,
    }
    result = await create_new_campaign(
        db_session, sample_source.id, data, "Av 5 # 10-20"
    )
    camp_id = result["campaign"].id

    detail = await get_campaign_detail(db_session, camp_id)
    assert detail is not None
    assert detail["campaign"].id == camp_id
    assert detail["source"].id == sample_source.id
    assert detail["source"].name == "Refugio Esteriliza Test"


# ── TC-09: Campaign detail for nonexistent campaign ──────────────────────────


@pytest.mark.asyncio
async def test_get_campaign_detail_not_found(
    db_session: AsyncSession,
) -> None:
    """Non-existent ID returns None."""
    detail = await get_campaign_detail(db_session, 99999)
    assert detail is None


# ── TC-10: find_nearby_campaigns excludes past campaigns ─────────────────────


@pytest.mark.asyncio
async def test_find_nearby_campaigns_excludes_past(
    db_session: AsyncSession,
    sample_source: Source,
) -> None:
    """Campaigns with starts_at in the past MUST NOT appear."""
    data = {
        "title": "Jornada Pasada",
        "municipality": "bogota",
        "starts_at": datetime.now() - timedelta(days=10),
        "species": ["canino"],
        "is_free": True,
    }
    await create_new_campaign(db_session, sample_source.id, data, "Cra 1 # 2-3")

    results = await find_nearby_campaigns(db_session, "bogota")
    assert not any(c.title == "Jornada Pasada" for c in results)
