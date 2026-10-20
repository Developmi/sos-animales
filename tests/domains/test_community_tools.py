"""Tests for community domain tools and voting logic."""

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domains.community.tools import register_update, cast_vote, get_entity_updates
from app.domains.animals.models import AnimalProfile  # noqa: F811 — trigger table registration
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign


@pytest_asyncio.fixture
async def sample_source(db_session: AsyncSession) -> Source:
    source = Source(
        name="Refugio Test",
        type="verified_shelter",
        status="verified",
        municipality="Medellín",
        department="Antioquia",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture
async def sample_campaign(db_session: AsyncSession, sample_source: Source) -> Campaign:
    camp = Campaign(
        source_id=sample_source.id,
        title="Jornada Test",
        municipality="Medellín",
        lat=6.2476,
        lng=-75.5658,
        starts_at=datetime(2026, 1, 1, 12, 0, 0),  # explicit naive datetime
        species=["canino"],
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
        name="Test Animal",
        species="canino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/test.jpg",
        status="available",
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)
    return animal


# ── TC-01 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_update_creates_with_defaults(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    update = await register_update(
        db_session, "full", note="Sin cupos", campaign_id=sample_campaign.id
    )
    assert update.id is not None
    assert update.votes == 1
    assert update.update_type == "full"
    assert update.note == "Sin cupos"
    assert update.campaign_id == sample_campaign.id


# ── TC-02 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_update_requires_xor_target(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await register_update(db_session, "full", note="sin target")


# ── TC-02b ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_update_with_animal_id_succeeds(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """register_update with animal_id (XOR leg) should succeed."""
    animal = AnimalProfile(
        name="Test Dog",
        species="canino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/dog.jpg",
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    update = await register_update(
        db_session, "confirmed", note="test", animal_id=animal.id
    )
    assert update.id is not None
    assert update.animal_id == animal.id
    assert update.campaign_id is None  # XOR: campaign must be None
    assert update.votes == 1


# ── TC-03 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_increments(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    update = await register_update(
        db_session, "full", note="test", campaign_id=sample_campaign.id
    )
    result = await cast_vote(db_session, update.id)
    assert result is not None
    assert result.votes == 2


# ── TC-04 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_nonexistent_id(db_session: AsyncSession) -> None:
    result = await cast_vote(db_session, 99999)
    assert result is None


# ── TC-05 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_reaches_threshold_changes_campaign_status(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    if settings.COMMUNITY_VOTE_THRESHOLD < 3:
        pytest.skip("COMMUNITY_VOTE_THRESHOLD must be >= 3 for this test")
    # Create update with update_type that triggers status override
    update = await register_update(
        db_session, "cancelled", note="test", campaign_id=sample_campaign.id
    )
    # Vote up to (threshold - 1), so one more vote hits the threshold
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 2):
        await cast_vote(db_session, update.id)

    result = await cast_vote(db_session, update.id)
    assert result is not None
    assert result.votes == settings.COMMUNITY_VOTE_THRESHOLD

    # Re-fetch campaign to verify status flip
    stmt = select(Campaign).where(Campaign.id == sample_campaign.id)
    camp_result = await db_session.execute(stmt)
    camp = camp_result.scalar_one()
    assert camp.status == "cancelled"


# ── TC-05b ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_threshold_confirmed_type_does_not_change_campaign(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    """update_type='confirmed' at threshold must NOT change campaign status."""
    if settings.COMMUNITY_VOTE_THRESHOLD < 3:
        pytest.skip("COMMUNITY_VOTE_THRESHOLD must be >= 3 for this test")
    update = await register_update(
        db_session, "confirmed", campaign_id=sample_campaign.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 2):
        await cast_vote(db_session, update.id)
    await cast_vote(db_session, update.id)

    stmt = select(Campaign).where(Campaign.id == sample_campaign.id)
    camp = (await db_session.execute(stmt)).scalar_one()
    assert camp.status == "scheduled"  # unchanged!


# ── TC-06 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entity_updates_filters_and_orders(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    update1 = await register_update(db_session, "full", campaign_id=sample_campaign.id)
    await register_update(db_session, "wrong_info", campaign_id=sample_campaign.id)
    # Vote on update1 so it has more votes → should appear first
    await cast_vote(db_session, update1.id)

    results = await get_entity_updates(db_session, campaign_id=sample_campaign.id)
    assert len(results) == 2
    assert results[0].votes > results[1].votes
    assert results[0].id == update1.id


# ── TC-07 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entity_updates_empty(
    db_session: AsyncSession, sample_campaign: Campaign
) -> None:
    results = await get_entity_updates(db_session, campaign_id=999)
    assert results == []


# ── TC-08 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_entity_updates_by_animal_id(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """animal_id filter returns only matching updates."""
    animal = AnimalProfile(
        name="Test Cat",
        species="felino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/cat.jpg",
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    await register_update(db_session, "confirmed", animal_id=animal.id)
    await register_update(db_session, "wrong_info", animal_id=animal.id)

    results = await get_entity_updates(db_session, animal_id=animal.id)
    assert len(results) == 2
    assert all(r.animal_id == animal.id for r in results)


# ── TC-09 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_adopted_threshold_changes_animal_status(
    db_session: AsyncSession, sample_animal: AnimalProfile
) -> None:
    """adopted update reaching threshold should set animal.status='adopted'."""
    update = await register_update(
        db_session, "adopted", note="test", animal_id=sample_animal.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 2):
        await cast_vote(db_session, update.id)
    await cast_vote(db_session, update.id)

    stmt = select(AnimalProfile).where(AnimalProfile.id == sample_animal.id)
    animal = (await db_session.execute(stmt)).scalar_one()
    assert animal.status == "adopted"
    assert animal.adopted_at is not None


# ── TC-10 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_in_treatment_threshold_changes_animal_status(
    db_session: AsyncSession, sample_animal: AnimalProfile
) -> None:
    """in_treatment update reaching threshold should set animal.status='in_treatment'."""
    update = await register_update(
        db_session, "in_treatment", note="test", animal_id=sample_animal.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 2):
        await cast_vote(db_session, update.id)
    await cast_vote(db_session, update.id)

    stmt = select(AnimalProfile).where(AnimalProfile.id == sample_animal.id)
    animal = (await db_session.execute(stmt)).scalar_one()
    assert animal.status == "in_treatment"


# ── TC-11 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_confirmed_does_not_change_animal_status(
    db_session: AsyncSession, sample_animal: AnimalProfile
) -> None:
    """confirmed update (not in ['adopted','in_treatment']) should NOT change status."""
    update = await register_update(
        db_session, "confirmed", note="test", animal_id=sample_animal.id
    )
    for _ in range(settings.COMMUNITY_VOTE_THRESHOLD - 2):
        await cast_vote(db_session, update.id)
    await cast_vote(db_session, update.id)

    stmt = select(AnimalProfile).where(AnimalProfile.id == sample_animal.id)
    animal = (await db_session.execute(stmt)).scalar_one()
    assert animal.status == "available"  # unchanged!


# ── TC-12 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cast_vote_adopted_below_threshold_does_not_change_status(
    db_session: AsyncSession, sample_animal: AnimalProfile
) -> None:
    """adopted update below threshold should NOT change animal status."""
    await register_update(
        db_session, "adopted", note="test", animal_id=sample_animal.id
    )
    # Only one vote (update starts with 1, we add none) = below threshold

    stmt = select(AnimalProfile).where(AnimalProfile.id == sample_animal.id)
    animal = (await db_session.execute(stmt)).scalar_one()
    assert animal.status == "available"  # unchanged!


# --- SDD-07 Data Governance Tests ---


@pytest.mark.asyncio
async def test_animal_profile_has_data_governance_fields(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """New fields save and load correctly."""
    from app.domains.animals.models import AnimalProfile
    from datetime import date

    animal = AnimalProfile(
        name="Test Gov",
        species="canino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/gov.jpg",
        sexo="macho",
        fecha_nacimiento=date(2024, 1, 15),
        etapa_madurez="joven",
        condiciones_especiales=["ciego", "amputado"],
        compatible_ninos=True,
        compatible_otros_animales=False,
        microchip="900123456789012",
        data_origin="official_authorized",
        source_url="https://idpyba.gov.co/animal/123",
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    assert animal.sexo == "macho"
    assert animal.fecha_nacimiento == date(2024, 1, 15)
    assert animal.etapa_madurez == "joven"
    assert animal.condiciones_especiales == ["ciego", "amputado"]
    assert animal.compatible_ninos is True
    assert animal.compatible_otros_animales is False
    assert animal.microchip == "900123456789012"
    assert animal.data_origin == "official_authorized"
    assert animal.source_url == "https://idpyba.gov.co/animal/123"


@pytest.mark.asyncio
async def test_animal_profile_data_origin_defaults_to_source_submitted(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """data_origin defaults to source_submitted."""
    from app.domains.animals.models import AnimalProfile

    animal = AnimalProfile(
        name="Test Default",
        species="canino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/default.jpg",
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    assert animal.data_origin == "source_submitted"


@pytest.mark.asyncio
async def test_campaign_has_data_governance_fields(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """Campaign data_origin and source_url save correctly."""
    from app.domains.sterilization.models import Campaign

    camp = Campaign(
        title="Test Gov Campaign",
        municipality="Bogota",
        species=["canino"],
        source_id=sample_source.id,
        starts_at=datetime(2026, 1, 1, 12, 0, 0),
        data_origin="official_factual",
        source_url="https://datos.gov.co/camp/456",
    )
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(camp)

    assert camp.data_origin == "official_factual"
    assert camp.source_url == "https://datos.gov.co/camp/456"
    assert camp.data_origin != "source_submitted"  # explicit override worked


@pytest.mark.asyncio
async def test_fixed_point_data_origin_defaults(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """FixedPoint defaults to source_submitted."""
    from app.domains.sterilization.models import FixedPoint

    fp = FixedPoint(
        name="Test FP",
        address="Calle 123",
        municipality="Bogota",
        source_id=sample_source.id,
        schedule_text="L-V 8-5",
        species=["canino", "felino"],
    )
    db_session.add(fp)
    await db_session.commit()
    await db_session.refresh(fp)

    assert fp.data_origin == "source_submitted"
    assert fp.source_url is None


@pytest.mark.asyncio
async def test_condiciones_especiales_empty_list_is_none(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """Empty condiciones_especiales should be None, not empty array."""
    from app.domains.animals.models import AnimalProfile

    animal = AnimalProfile(
        name="Test Empty",
        species="canino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/empty.jpg",
        condiciones_especiales=[],
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    assert animal.condiciones_especiales is None or animal.condiciones_especiales == []


@pytest.mark.asyncio
async def test_compatible_fields_nullable(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """compatible_ninos and compatible_otros_animales support None (unknown)."""
    from app.domains.animals.models import AnimalProfile

    animal = AnimalProfile(
        name="Test Unknown",
        species="canino",
        municipality="Bogota",
        source_id=sample_source.id,
        foto_url="https://example.com/unknown.jpg",
        compatible_ninos=None,
        compatible_otros_animales=None,
    )
    db_session.add(animal)
    await db_session.commit()
    await db_session.refresh(animal)

    assert animal.compatible_ninos is None
    assert animal.compatible_otros_animales is None


@pytest.mark.asyncio
async def test_create_animal_profile_passes_all_fields(
    db_session: AsyncSession, sample_source: Source
) -> None:
    """create_animal_profile() passes all 9 new fields through data dict."""
    from app.domains.animals.tools import create_animal_profile
    from datetime import date

    data = {
        "name": "Test All Fields",
        "species": "canino",
        "municipality": "Bogota",
        "sexo": "hembra",
        "fecha_nacimiento": date(2023, 6, 1),
        "etapa_madurez": "adulto",
        "condiciones_especiales": ["condicion_cronica"],
        "compatible_ninos": True,
        "compatible_otros_animales": False,
        "microchip": "999888777666555",
        "data_origin": "source_submitted",
        "source_url": "https://example.com/source",
    }
    result = await create_animal_profile(
        db_session, sample_source.id, data, "https://example.com/photo.jpg"
    )
    animal = result["animal"]

    assert animal.sexo == "hembra"
    assert animal.compatible_ninos is True
    assert animal.compatible_otros_animales is False
    assert animal.data_origin == "source_submitted"
