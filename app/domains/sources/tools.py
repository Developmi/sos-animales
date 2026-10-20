"""Pure business logic functions for the sources domain.

- register_source: registers a new shelter/organization in pending status.
- verify_source: promotes status to verified upon veterinary audit completion.
- list_sources: active sources filtered by municipality.
- get_source: retrieves source by primary key ID.
"""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.sources.models import Source
from app.domains.sources.schemas import SourceRegisterIn
from sqlalchemy import select


async def register_source(db: AsyncSession, data: SourceRegisterIn) -> Source:
    existing = await db.execute(
        select(Source).where(
            Source.name == data.name,
            Source.municipality == data.municipality,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Ya existe una fuente con ese nombre y municipio")

    new_source = Source(
        name=data.name,
        type=data.type,
        status="pending",  # Business rule: all registrations start in pending status
        municipality=data.municipality,
        department=data.department,
        contact_email=data.contact_email,
        contact_whatsapp=data.contact_whatsapp,
        contact_url=str(data.contact_url) if data.contact_url else None,
    )
    db.add(new_source)
    await db.commit()
    await db.refresh(new_source)
    return new_source


async def get_source(db: AsyncSession, source_id: int) -> Source | None:
    """Find a source by its primary key ID."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    return result.scalar_one_or_none()


async def list_sources(
    db: AsyncSession,
    municipality: str | None = None,
    limit: int = 50,
) -> list[Source]:
    """List active sources, optionally filtered by municipality.

    ponytail: ilike, upgrade to tsvector if search counts exceed 5k rows.
    """
    # ponytail: ilike for substring match
    stmt = select(Source).where(Source.is_active)
    if municipality:
        stmt = stmt.where(Source.municipality.ilike(f"%{municipality}%"))
    stmt = stmt.order_by(Source.name).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def verify_source(db: AsyncSession, source_id: int) -> Source | None:
    """Promote source status to 'verified' and record verification timestamp."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if source:
        source.status = "verified"
        source.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(source)
    return source
