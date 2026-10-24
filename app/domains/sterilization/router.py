"""HTMX endpoints for the sterilization domain.

- GET /sterilization/search — full search landing page
- GET /sterilization/campaigns — HTMX fragment with search results
- GET /sterilization/campaigns/{id} — detailed view of a campaign
- GET /sterilization/fixed-points/new & POST /sterilization/fixed-points/new — fixed veterinary points
"""

from fastapi import (
    APIRouter,
    Request,
    Depends,
    Query,
    HTTPException,
    Form,
    BackgroundTasks,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from sqlalchemy import select

from app.database import get_db
from app.domains.auth.middleware import require_auth

from app.shared.email import send_pin_email_sync
from app.domains.sterilization.tools import (
    find_nearby_campaigns,
    create_new_campaign,
    create_new_fixed_point,
)
from app.domains.sterilization.tools import get_campaign_detail, get_freshness_status
from app.domains.sterilization.tools import confirm_entity_freshness
from app.config import settings
from app.domains.sources.models import Source
from app.domains.sterilization.schemas import CampaignCreate, FixedPointCreate
from app.shared.geo import get_active_municipalities, get_grouped_municipalities
from app.shared.models.location import Department, Municipality

router = APIRouter(prefix="/sterilization", tags=["sterilization"])

templates = Jinja2Templates(
    directory=["app/domains/sterilization/templates", "app/shared/templates"]
)
templates.env.globals["settings"] = settings


@router.get("/new", response_class=HTMLResponse)
async def new_campaign_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render creation form for publishing a sterilization campaign."""
    try:
        result = await db.execute(select(Source).where(Source.is_active))
        sources = result.scalars().all()
        grouped = await get_grouped_municipalities(db)
    except Exception:
        sources = []
        grouped = {}

    return templates.TemplateResponse(
        request=request,
        name="campaign_form.html",
        context={"sources": sources, "grouped_municipalities": grouped},
    )


@router.post("/new", response_class=HTMLResponse)
async def post_new_campaign(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_auth),
    source_id: int = Form(...),
    title: str = Form(...),
    municipality: str = Form(...),
    address: str = Form(...),
    starts_at: datetime = Form(...),
    species: list[str] = Form(...),
    capacity: int | None = Form(None),
    is_free: bool = Form(False),
    requirements: str | None = Form(None),
    booking_url: str | None = Form(None),
    source_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Process form submission, geocode location, and persist campaign in database."""
    # Validate with Pydantic schema before delegating to tools
    try:
        campaign_data = CampaignCreate(
            title=title,
            municipality=municipality,
            starts_at=starts_at,
            species=species,
            capacity=capacity,
            is_free=is_free,
            requirements=requirements,
            booking_url=booking_url,
            source_url=source_url,
        )
        result = await create_new_campaign(
            db, source_id, campaign_data.model_dump(), address
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<article><header>Error de Validación</header><p>{str(e)}</p></article>",
            status_code=400,
        )

    camp = result["campaign"]
    pin = result["raw_pin"]
    contact_email = result["contact_email"]

    background_tasks.add_task(send_pin_email_sync, contact_email, camp.title, pin)

    msg_mapa = (
        "📍 Ubicación detectada en el mapa."
        if camp.lat
        else "⚠️ No pudimos ubicar la dirección exacta."
    )

    # Success confirmation message
    return HTMLResponse(
        content=f"<article><header style='background-color: var(--pico-primary-background); color: white;'>¡Jornada Publicada!</header>"
        f"La jornada <strong>{camp.title}</strong> está en línea.<br>{msg_mapa}<br><br>"
        f"✅ <strong>Te enviamos el PIN de administración al correo:</strong> <mark>{contact_email}</mark><br>"
        f"<small>Revisa tu bandeja de entrada o spam. Lo necesitarás si debes cancelar o modificar la jornada.</small></article>"
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request) -> HTMLResponse:
    """Render search landing page with filters."""
    return templates.TemplateResponse(request=request, name="index.html", context={})


@router.get("/campaigns", response_class=HTMLResponse)
async def get_campaigns_htmx(
    request: Request,
    municipality: str = Query("bogota"),
    species: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """HTMX endpoint returning campaign search results matching filters."""
    campaigns = await find_nearby_campaigns(db, municipality, species)

    return templates.TemplateResponse(
        request=request, name="map_results.html", context={"campaigns": campaigns}
    )


@router.get("/fixed-points/new", response_class=HTMLResponse)
async def new_fixed_point_form(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    result = await db.execute(select(Source).where(Source.is_active))
    grouped = await get_grouped_municipalities(db)
    return templates.TemplateResponse(
        request,
        "fixed_point_form.html",
        {"sources": result.scalars().all(), "grouped_municipalities": grouped},
    )


@router.post("/fixed-points/new", response_class=HTMLResponse)
async def post_new_fixed_point(
    _: None = Depends(require_auth),
    source_id: int = Form(...),
    name: str = Form(...),
    municipality: str = Form(...),
    address: str = Form(...),
    schedule_text: str = Form(...),
    species: list[str] = Form(...),
    is_free: bool = Form(False),
    requirements: str | None = Form(None),
    source_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    # Validate with Pydantic schema before delegating to tools
    try:
        fp_data = FixedPointCreate(
            name=name,
            municipality=municipality,
            address=address,
            schedule_text=schedule_text,
            species=species,
            is_free=is_free,
            requirements=requirements,
            source_url=source_url,
        )
        fp = await create_new_fixed_point(db, source_id, fp_data.model_dump())
    except Exception as e:
        return HTMLResponse(
            content=f"<article><header>Error</header><p>{str(e)}</p></article>",
            status_code=400,
        )
    return HTMLResponse(
        f"<article><header>¡Punto Fijo Registrado!</header>El punto <strong>{fp.name}</strong> aparecerá ahora en el mapa de {fp.municipality}.</article>"
    )


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail_page(
    request: Request, campaign_id: int, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Detailed view for a sterilization campaign."""
    detail = await get_campaign_detail(db, campaign_id)

    if not detail:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")

    freshness_status = get_freshness_status(detail["campaign"])
    return templates.TemplateResponse(
        request=request,
        name="campaign_detail.html",
        context={
            "campaign": detail["campaign"],
            "source": detail["source"],
            "freshness_status": freshness_status,
        },
    )


@router.post("/confirm/{entity_type}/{entity_id}", response_class=HTMLResponse)
async def confirm_freshness(
    request: Request,
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Update last_confirmed_at to current timestamp to renew freshness."""
    ok = await confirm_entity_freshness(db, entity_type, entity_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"{entity_type} #{entity_id} no encontrado",
        )
    labels = {"campaign": "Jornada", "fixed-point": "Punto fijo"}
    label = labels.get(entity_type, entity_type)
    return HTMLResponse(f"✅ {label} confirmada — frescura renovada.")


@router.get("/municipality-options", response_class=HTMLResponse)
async def get_municipality_options(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """HTMX: return <option> elements of municipalities grouped by department."""
    stmt = (
        select(Department, Municipality)
        .join(Municipality, Department.id == Municipality.department_id)
        .order_by(Department.name, Municipality.name)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Group: { "Antioquia": [Municipality, ...], ... }
    grouped: dict[str, list[Municipality]] = {}
    for dept, mun in rows:
        if dept.name not in grouped:
            grouped[dept.name] = []
        grouped[dept.name].append(mun)

    return templates.TemplateResponse(
        request=request,
        name="municipality_options.html",
        context={"grouped": grouped},
    )


@router.get("/department-options", response_class=HTMLResponse)
async def get_department_options(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """HTMX: return <option> elements of departments."""
    result = await db.execute(select(Department).order_by(Department.name))
    departments = result.scalars().all()

    options_html = "".join(
        f'<option value="{d.name.lower()}">{d.name}</option>' for d in departments
    )
    return HTMLResponse(options_html)


@router.get("/active-municipality-options", response_class=HTMLResponse)
async def get_active_municipality_options(
    request: Request,
    domain: str = Query("all"),
    selected: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """HTMX: return <option> elements of ONLY active municipalities that have records."""
    munis = await get_active_municipalities(db, domain=domain)
    options = ['<option value="">Todas las ciudades</option>']
    for m in munis:
        val = m.lower()
        is_sel = " selected" if selected and selected.lower() == val else ""
        options.append(f'<option value="{val}"{is_sel}>{m}</option>')
    return HTMLResponse("".join(options))
