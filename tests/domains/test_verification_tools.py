"""Tests for verification domain tools and inspection checklists."""

import pytest
from datetime import datetime, timedelta, UTC
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sources.models import Source
from app.domains.verification.tools import (
    create_verification_request,
    schedule_visit,
    record_checklist_result,
)


@pytest.mark.asyncio
async def test_successful_verification_flow(db_session: AsyncSession) -> None:
    # 1. Create test source (starts in pending status)
    source = Source(
        name="Fundación Test",
        type="verified_shelter",
        status="pending",
        municipality="bogota",
        department="cundinamarca",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    # 2. Create verification request
    req = await create_verification_request(
        db_session, source.id, evidence="Fotos adjuntas"
    )
    assert req.status == "pending"

    # 3. Schedule the visit
    visit = await schedule_visit(
        db_session,
        request_id=req.id,
        visit_type="presencial",
        scheduled_at=(datetime.now(UTC) + timedelta(days=2)).replace(tzinfo=None),
        visitor_name="Dr. Vet",
    )
    assert visit.id is not None
    assert req.status == "scheduled"  # Request status must transition to scheduled

    # 4. Record successful checklist
    checklist_data = [
        {"criterion": "Instalaciones limpias", "passed": True},
        {"criterion": "Registros al día", "passed": True},
    ]

    result = await record_checklist_result(db_session, visit.id, checklist_data)

    # 5. Assert success
    assert result is True
    assert req.status == "done"

    # 6. Source must transition to verified
    await db_session.refresh(source)
    assert source.status == "verified"
    assert source.verified_at is not None


@pytest.mark.asyncio
async def test_rejected_verification_flow(db_session: AsyncSession) -> None:
    # Similar flow but with a failing criterion
    source = Source(
        name="Fundación Rechazada",
        type="community",
        status="pending",
        municipality="cali",
        department="valle",
    )
    db_session.add(source)
    await db_session.commit()

    req = await create_verification_request(db_session, source.id)
    visit = await schedule_visit(
        db_session, req.id, "remota", datetime.now(UTC).replace(tzinfo=None), "Admin"
    )

    # Checklist with a failure
    checklist_data = [
        {"criterion": "Instalaciones limpias", "passed": True},
        {"criterion": "Registros al día", "passed": False, "notes": "Faltan vacunas"},
    ]

    result = await record_checklist_result(db_session, visit.id, checklist_data)

    # Assertions
    assert result is False
    assert req.status == "rejected"

    await db_session.refresh(source)
    assert source.status == "pending"  # Remains pending, verification rejected
