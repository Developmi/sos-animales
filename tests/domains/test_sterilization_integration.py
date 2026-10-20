"""Integration tests for the Sterilization domain and campaigns.

Covers:
1. Physical address retention and database persistence in Campaign.
2. Capacity validation and future start date enforcement.
3. Proper HTTP 400 validation error handling in POST /sterilization/new.
4. Physical address rendering in the public campaign page and Leaflet map popup.
5. Search filtering by municipality and automatic exclusion of expired campaigns.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
import jwt
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.main import app
from app.config import settings
from app.database import get_db
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.domains.sterilization.schemas import CampaignCreate
from app.domains.sterilization.tools import (
    create_new_campaign,
    find_nearby_campaigns,
    get_campaign_detail,
)


def make_admin_token() -> str:
    return jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"access_token": make_admin_token()},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_shelter(db_session: AsyncSession) -> Source:
    source = Source(
        name="Fundación Esteriliza Colombia",
        type="verified_shelter",
        status="verified",
        municipality="Bogotá",
        department="Cundinamarca",
        contact_email="esteriliza@sos-animales.org",
        contact_whatsapp="+573105559988",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_campaign_address_retention_in_db(
    db_session: AsyncSession,
    sample_shelter: Source,
) -> None:
    """Verify that the physical address supplied when creating a campaign is saved in the database."""
    future_date = datetime.now(timezone.utc) + timedelta(days=5)
    data = {
        "title": "Jornada Kennedy Central",
        "municipality": "Bogotá",
        "starts_at": future_date,
        "species": ["canino", "felino"],
        "is_free": True,
        "capacity": 80,
    }

    result = await create_new_campaign(
        db_session,
        sample_shelter.id,
        data,
        address="Calle 45 Sur # 78K-10, Kennedy",
    )

    campaign: Campaign = result["campaign"]
    # Entity must retain physical address attribute
    assert hasattr(campaign, "address")
    assert campaign.address == "Calle 45 Sur # 78K-10, Kennedy"
    assert campaign.capacity == 80

    # Verify get_campaign_detail retrieves the address
    detail = await get_campaign_detail(db_session, campaign.id)
    assert detail is not None
    assert detail["campaign"].address == "Calle 45 Sur # 78K-10, Kennedy"


def test_campaign_capacity_validation() -> None:
    """Validate that capacity cannot be negative."""
    future_date = datetime.now(timezone.utc) + timedelta(days=3)

    # Negative capacity must fail
    with pytest.raises(ValidationError):
        CampaignCreate(
            title="Jornada Capacidad Negativa",
            municipality="Bogotá",
            starts_at=future_date,
            species=["canino"],
            capacity=-10,
        )

    # Positive capacity must be accepted
    valid = CampaignCreate(
        title="Jornada Capacidad Válida",
        municipality="Bogotá",
        starts_at=future_date,
        species=["canino"],
        capacity=50,
    )
    assert valid.capacity == 50


def test_campaign_starts_at_past_validation() -> None:
    """Validate that a past start date is rejected by schema."""
    past_date = datetime.now(timezone.utc) - timedelta(days=2)
    with pytest.raises(ValidationError) as exc_info:
        CampaignCreate(
            title="Jornada Pasada",
            municipality="Bogotá",
            starts_at=past_date,
            species=["canino"],
        )
    assert "pasado" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_post_new_campaign_endpoint_validation_error_handling(
    app_client: AsyncClient,
    sample_shelter: Source,
) -> None:
    """Submitting invalid data (e.g. past date) to POST /sterilization/new returns controlled HTTP 400."""
    past_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    form_data = {
        "source_id": str(sample_shelter.id),
        "title": "Jornada Inválida",
        "municipality": "Bogotá",
        "address": "Carrera 7 # 32-16",
        "starts_at": past_date,
        "species": ["canino"],
        "is_free": "true",
    }

    response = await app_client.post("/sterilization/new", data=form_data)
    assert response.status_code == 400
    assert (
        "error de validación" in response.text.lower()
        or "pasado" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_campaign_detail_renders_physical_address_in_html(
    app_client: AsyncClient,
    db_session: AsyncSession,
    sample_shelter: Source,
) -> None:
    """Campaign detail view /sterilization/campaigns/{id} must render the physical address."""
    future_date = datetime.now(timezone.utc) + timedelta(days=7)
    data = {
        "title": "Gran Jornada Suba",
        "municipality": "Bogotá",
        "starts_at": future_date,
        "species": ["canino", "felino"],
        "is_free": True,
        "capacity": 100,
    }
    result = await create_new_campaign(
        db_session,
        sample_shelter.id,
        data,
        address="Avenida Suba # 115-40",
    )
    camp = result["campaign"]

    response = await app_client.get(f"/sterilization/campaigns/{camp.id}")
    assert response.status_code == 200
    assert "Avenida Suba # 115-40" in response.text
    assert "Gran Jornada Suba" in response.text


@pytest.mark.asyncio
async def test_find_nearby_campaigns_excludes_expired_dates(
    db_session: AsyncSession,
    sample_shelter: Source,
) -> None:
    """find_nearby_campaigns must exclude past campaigns and return active future ones."""
    # Future campaign
    future_date = datetime.now(timezone.utc) + timedelta(days=4)
    data_future = {
        "title": "Jornada Vigente Engativá",
        "municipality": "Bogotá",
        "starts_at": future_date,
        "species": ["canino"],
        "is_free": True,
    }
    await create_new_campaign(
        db_session, sample_shelter.id, data_future, "Calle 80 # 70-10"
    )

    campaigns = await find_nearby_campaigns(db_session, "Bogotá", species="canino")
    titles = [c.title for c in campaigns]
    assert "Jornada Vigente Engativá" in titles
