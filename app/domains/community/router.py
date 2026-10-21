"""HTMX endpoints for the community domain.

- GET /community/update — render reporting form.
- POST /community/update — submit community report.
- GET /community/list — list community reports for an entity.
- POST /community/{update_id}/vote — cast vote with anti-spam rate limiting.
"""

from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.community.tools import register_update, get_entity_updates, cast_vote
from app.shared.security import check_rate_limit, mark_as_voted, has_voted_recently
from app.domains.community.schemas import CommunityUpdateCreate

router = APIRouter(prefix="/community", tags=["community"])

templates = Jinja2Templates(
    directory=["app/domains/community/templates", "app/shared/templates"]
)
templates.env.globals["settings"] = settings


@router.get("/update", response_class=HTMLResponse)
async def get_update_form(
    request: Request,
    campaign_id: int | None = Query(None),
    animal_id: int | None = Query(None),
) -> HTMLResponse:
    """Return HTML fragment for the reporting form."""
    return templates.TemplateResponse(
        request=request,
        name="update_form.html",
        context={"campaign_id": campaign_id, "animal_id": animal_id},
    )


@router.post("/update", response_class=HTMLResponse)
async def post_update(
    request: Request,
    update_type: str = Form(...),
    note: str | None = Form(None),
    campaign_id: int | None = Form(None),
    animal_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Save community report and return confirmation fragment."""
    # Validate with Pydantic before delegating to tools
    try:
        CommunityUpdateCreate(
            update_type=update_type,
            note=note,
            campaign_id=campaign_id,
            animal_id=animal_id,
        )
        new_update = await register_update(
            db, update_type, note, campaign_id, animal_id
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<div style='background: #FFF1F2; border: 1px solid #FECDD3; border-radius: 8px; padding: 14px; color: #E11D48; font-size: 13px;'><strong>Error de validación:</strong> {str(e)}</div>",
            status_code=400,
        )

    # 2. Block the creator from immediate self-voting
    client_ip = request.client.host if request.client else "127.0.0.1"
    await mark_as_voted(client_ip, new_update.id)

    # Build confirmation response
    response = templates.TemplateResponse(
        request=request, name="update_confirmation.html", context={}
    )

    response.headers["HX-Trigger"] = "newCommunityUpdate"

    return response


@router.get("/list", response_class=HTMLResponse)
async def list_updates_htmx(
    request: Request,
    campaign_id: int | None = Query(None),
    animal_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Return HTML fragment with list of community reports."""
    updates = await get_entity_updates(db, campaign_id, animal_id)
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Identify report IDs the client IP has already voted for
    voted_ids = [u.id for u in updates if await has_voted_recently(client_ip, u.id)]

    return templates.TemplateResponse(
        request=request,
        name="updates_list.html",
        context={
            "updates": updates,
            "threshold": settings.COMMUNITY_VOTE_THRESHOLD,
            "voted_ids": voted_ids,
        },
    )


@router.post("/{update_id}/vote", response_class=HTMLResponse)
async def vote_for_update_htmx(
    request: Request, update_id: int, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Record vote and return updated status button."""

    # 1. Retrieve client IP
    client_ip = request.client.host if request.client else "127.0.0.1"

    # 2. Check rate limit window (900 seconds = 15 minutes)
    if not await check_rate_limit(client_ip, update_id, window_seconds=900):
        # HTMX temporarily replaces vote button with cooldown indicator
        return HTMLResponse(
            "<span class='vote-btn-cooldown' title='Debes esperar antes de volver a validar'>"
            "⏳ Ya votaste. Espera 15 min.</span>"
        )

    # 3. If within rate limits, persist the vote
    update_obj = await cast_vote(db, update_id)
    if not update_obj:
        return HTMLResponse(
            content="<span class='vote-btn-cooldown'>Reporte no encontrado</span>",
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="vote_status.html",
        context={
            "update": update_obj,
            "threshold": settings.COMMUNITY_VOTE_THRESHOLD,
            "voted_ids": [update_id],
        },
    )
