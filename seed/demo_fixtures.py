"""Single-responsibility seed module for synthetic development/QA demo fixtures.

Must ONLY be invoked explicitly in development environments (`python -m seed --demo`).
Never executed automatically by production container entrypoints.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.domains.verification.tools import create_verification_request, schedule_visit


async def populate_demo_data(db: AsyncSession) -> None:
    """Insert synthetic demo shelters, campaigns, and verification visits (idempotent)."""
    existing = await db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.title.ilike("%Jornada Zoonosis%")
        )
    )
    if existing and existing > 0:
        print("  ↪ Demo fixtures already present, skipping.")
        return

    result = await db.execute(select(Source).limit(1))
    source = result.scalar_one_or_none()
    if not source:
        print("  ℹ️  Creating demo shelter source...")
        source = Source(
            name="Fundación SOS Animales Demo",
            type="verified_shelter",
            status="verified",
            municipality="bogota",
            department="bogota",
            contact_email="demo@sos-animales.org",
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        print(f"  ✅ Demo shelter created (id={source.id})")

    print("  🧪 Inserting demo sterilization campaigns...")
    camp1 = Campaign(
        source_id=source.id,
        title="Gran Jornada Zoonosis - Kennedy",
        municipality="bogota",
        lat=4.6300,
        lng=-74.1500,
        starts_at=datetime.now() + timedelta(days=3),
        species=["canino", "felino"],
        is_free=True,
        status="scheduled",
    )
    camp2 = Campaign(
        source_id=source.id,
        title="Esterilización a Bajo Costo - El Poblado",
        municipality="medellin",
        lat=6.2088,
        lng=-75.5678,
        starts_at=datetime.now() + timedelta(days=10),
        species=["felino"],
        is_free=False,
        status="scheduled",
    )
    db.add_all([camp1, camp2])
    await db.commit()
    print("  ✅ Demo campaigns inserted.")

    source_dudosa = Source(
        name="Fundación Dudosa",
        type="community",
        status="pending",
        municipality="cali",
        department="valle",
        contact_email="dudosa@test.com",
    )
    db.add(source_dudosa)
    await db.commit()
    await db.refresh(source_dudosa)

    req_ok = await create_verification_request(db, source.id)
    await schedule_visit(
        db,
        req_ok.id,
        "presencial",
        datetime.now(UTC).replace(tzinfo=None),
        "Inspector de prueba",
    )
    req_fail = await create_verification_request(db, source_dudosa.id)
    visit_fail = await schedule_visit(
        db,
        req_fail.id,
        "remota",
        datetime.now(UTC).replace(tzinfo=None),
        "Inspector Riguroso",
    )
    print(f"  ⚠️  Demo rejection visit scheduled with ID: {visit_fail.id}")
    print("  ✅ Demo fixtures ready.")


async def seed_demo_fixtures() -> None:
    """Open an async session and populate synthetic demo fixtures for local development."""
    async with AsyncSessionLocal() as db:
        print("\n🧪 Loading synthetic development demo fixtures...")
        await populate_demo_data(db)
