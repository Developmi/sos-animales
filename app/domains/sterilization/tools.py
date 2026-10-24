"""Pure business logic functions for the sterilization domain.

- find_nearby_campaigns: search campaigns by municipality, species, and status.
- get_campaign_detail: full campaign detail joined with responsible source.
- create_new_fixed_point: register fixed sterilization clinic/location.
- create_new_campaign: register new campaign event with geocoding and management PIN.
- confirm_entity_freshness: update freshness timestamp.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign, FixedPoint
from app.shared.geo import geocode_address
from app.shared.security import generate_pin, hash_pin


async def create_new_fixed_point(
    db: AsyncSession, source_id: int, data: dict[str, Any]
) -> FixedPoint:
    """Register a permanent fixed point with geocoded coordinates."""
    existing = await db.execute(
        select(FixedPoint).where(
            FixedPoint.name == data["name"],
            FixedPoint.source_id == source_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Ya existe un punto fijo con ese nombre para esta fuente")

    lat, lng = await geocode_address(data["address"], data["municipality"])

    fp = FixedPoint(
        source_id=source_id,
        name=data["name"],
        address=data["address"],
        lat=lat,
        lng=lng,
        municipality=data["municipality"],
        schedule_text=data["schedule_text"],
        species=data["species"],
        is_free=data["is_free"],
        requirements=data.get("requirements"),
        data_origin=data.get("data_origin", "source_submitted"),
        source_url=data.get("source_url"),
    )
    db.add(fp)
    await db.commit()
    return fp


# ── Freshness Policy ─────────────────────────────────────────────────────


def get_freshness_days(obj: Campaign | FixedPoint) -> int | None:
    """Calculate days elapsed since last confirmation timestamp.

    Returns None if never confirmed (created_at serves as baseline).
    """
    last = obj.last_confirmed_at or obj.created_at
    if last is None:
        return None
    delta = datetime.now(UTC) - last
    return delta.days


def get_freshness_status(obj: Campaign | FixedPoint) -> str:
    """Return freshness status according to system retention policy.

    - 'fresh': confirmed within threshold (≤ FRESHNESS_DAYS).
    - 'stale': unconfirmed (> FRESHNESS_DAYS, ≤ FRESHNESS_HIDE_DAYS).
    - 'hidden': unconfirmed (> FRESHNESS_HIDE_DAYS).
    - 'unknown': missing confirmation and creation timestamps.
    """
    days = get_freshness_days(obj)
    if days is None:
        return "unknown"
    if days > settings.FRESHNESS_HIDE_DAYS:
        return "hidden"
    if days > settings.FRESHNESS_DAYS:
        return "stale"
    return "fresh"


async def find_nearby_campaigns(
    db: AsyncSession,
    municipality: str,
    species: str | None = None,
    limit: int = 50,
) -> list[Campaign]:
    """Find scheduled campaigns in a municipality.

    Enforces freshness policy: hides campaigns unconfirmed for more than
    FRESHNESS_HIDE_DAYS days.
    """
    cutoff = datetime.now(UTC) - timedelta(days=settings.FRESHNESS_HIDE_DAYS)

    query = select(Campaign).where(
        Campaign.municipality.ilike(f"%{municipality}%"),
        Campaign.status == "scheduled",
        Campaign.starts_at >= datetime.now(UTC),
        # Hide stale data: fall back to created_at if last_confirmed_at is null
        func.coalesce(Campaign.last_confirmed_at, Campaign.created_at) >= cutoff,
    )

    if species:
        query = query.where(Campaign.species.contains([species]))

    query = query.order_by(Campaign.starts_at).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_campaign_detail(
    db: AsyncSession, campaign_id: int
) -> dict[str, Any] | None:
    """Retrieve full campaign details joined with organizing source."""
    query = (
        select(Campaign, Source)
        .join(Source, Campaign.source_id == Source.id)
        .where(Campaign.id == campaign_id)
    )
    result = await db.execute(query)
    row = result.first()

    if row:
        return {"campaign": row.Campaign, "source": row.Source}
    return None


async def create_new_campaign(
    db: AsyncSession, source_id: int, data: dict[str, Any], address: str
) -> dict[str, Any]:
    """Create a new campaign calculating geographical coordinates automatically."""

    existing = await db.execute(
        select(Campaign).where(
            Campaign.title == data["title"],
            Campaign.source_id == source_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Ya existe una jornada con ese título para esta fuente")

    # 1. Geocode coordinates from address and municipality
    lat, lng = await geocode_address(address, data["municipality"])

    # 2. Cryptographic security PIN
    raw_pin = generate_pin()

    new_camp = Campaign(
        source_id=source_id,
        title=data["title"],
        address=address,
        municipality=data["municipality"],
        lat=lat,
        lng=lng,
        starts_at=data["starts_at"],
        species=data["species"],
        capacity=data.get("capacity"),
        is_free=data["is_free"],
        requirements=data.get("requirements"),
        booking_url=data.get("booking_url"),
        status="scheduled",
        pin_hash=hash_pin(raw_pin),
        data_origin=data.get("data_origin", "source_submitted"),
        source_url=data.get("source_url"),
    )

    db.add(new_camp)
    await db.commit()
    await db.refresh(new_camp)

    # Fetch organizing source contact email
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    contact_email = source.contact_email if source else "sin-correo@test.com"

    return {"campaign": new_camp, "raw_pin": raw_pin, "contact_email": contact_email}


async def confirm_entity_freshness(
    db: AsyncSession, entity_type: str, entity_id: int
) -> bool:
    """Update last_confirmed_at to current timestamp.

    entity_type: "campaign" or "fixed-point"
    Returns True if record was found and updated, False otherwise.
    """
    now = datetime.now(UTC)

    if entity_type == "campaign":
        result = await db.execute(select(Campaign).where(Campaign.id == entity_id))
        obj = result.scalar_one_or_none()
    elif entity_type == "fixed-point":
        result = await db.execute(select(FixedPoint).where(FixedPoint.id == entity_id))
        obj = result.scalar_one_or_none()
    else:
        return False

    if obj is None:
        return False

    obj.last_confirmed_at = now
    await db.commit()
    return True
