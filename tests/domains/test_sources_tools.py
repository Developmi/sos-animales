"""Tests for sources domain tools and registration workflows."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.sources.tools import register_source
from app.domains.sources.schemas import SourceRegisterIn


@pytest.mark.asyncio
async def test_register_source(db_session: AsyncSession) -> None:
    # 1. Prepare test payload
    data = SourceRegisterIn(
        name="Fundación Test",
        type="verified_shelter",
        municipality="bogota",
        department="bogota",
        contact_email="test@fundacion.com",
    )

    # 2. Execute business logic
    source = await register_source(db_session, data)

    # 3. Assert proper creation
    assert source.id is not None
    assert source.name == "Fundación Test"
    assert source.status == "pending"  # Crucial business rule: starts in pending status
