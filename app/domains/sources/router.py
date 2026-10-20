"""HTMX endpoints for the sources domain.

- GET /sources/register — self-registration form (with Colombian statutory privacy notice).
- POST /sources/register — submit registration, creating source in pending status.
- GET /sources — directory of active sources filtered by municipality.
- GET /sources/{id} — public shelter profile with verified badge.
"""

from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.sources.schemas import SourceRegisterIn
from app.domains.sources.tools import register_source, get_source, list_sources
from app.domains.sterilization.models import Campaign
from app.domains.animals.models import AnimalProfile
from sqlalchemy import select as sql_select
from fastapi import HTTPException

router = APIRouter(prefix="/sources", tags=["sources"])

# Lookup templates in sources/templates and shared/templates
templates = Jinja2Templates(
    directory=["app/domains/sources/templates", "app/shared/templates"]
)


@router.get("/register", response_class=HTMLResponse)
async def get_register_form(request: Request) -> HTMLResponse:
    """Render self-registration form."""
    return templates.TemplateResponse(
        request=request, name="register_form.html", context={}
    )


@router.post("/register", response_class=HTMLResponse)
async def post_register_form(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    municipality: str = Form(...),
    department: str = Form(...),
    accept_terms: bool = Form(...),  # Mandatory for data privacy compliance
    contact_email: str | None = Form(None),
    contact_whatsapp: str | None = Form(None),
    contact_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Process self-registration form and return HTMX success fragment."""
    try:
        # Map HTML form payload to Pydantic schema
        data = SourceRegisterIn(
            name=name,
            type=type,
            municipality=municipality,
            department=department,
            contact_email=contact_email,
            contact_whatsapp=contact_whatsapp,
            contact_url=contact_url,
        )
        await register_source(db, data)
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="error_not_found.html",
            context={"message": str(e)},
            status_code=400,
        )

    # HTMX replaces form with confirmation message
    return templates.TemplateResponse(
        request=request, name="register_success.html", context={"name": name}
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_sources_view(
    request: Request,
    municipality: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Directory of active sources with optional municipality filter."""
    sources = await list_sources(db, municipality)
    return templates.TemplateResponse(
        request=request,
        name="source_list.html",
        context={"sources": sources, "municipality": municipality},
    )


@router.get("/{source_id}", response_class=HTMLResponse)
async def get_source_profile(
    request: Request, source_id: int, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Public profile view for an organization or shelter."""
    source = await get_source(db, source_id)

    if not source:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")

    # Fetch campaigns and animals belonging to this source
    camps_result = await db.execute(
        sql_select(Campaign)
        .where(Campaign.source_id == source_id)
        .order_by(Campaign.starts_at.desc())
    )
    campaigns = list(camps_result.scalars().all())

    animals_result = await db.execute(
        sql_select(AnimalProfile)
        .where(AnimalProfile.source_id == source_id)
        .order_by(AnimalProfile.created_at.desc())
    )
    animals = list(animals_result.scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="source_profile.html",
        context={
            "source": source,
            "campaigns": campaigns,
            "animals": animals,
        },
    )
