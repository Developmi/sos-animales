"""HTMX endpoints for the community domain.

- GET /community/update — render reporting form.
- POST /community/update — submit community report.
- GET /community/list — list community reports for an entity.
- POST /community/{update_id}/vote — cast vote with anti-spam rate limiting.
"""

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.community.schemas import CommunityUpdateCreate
from app.domains.community.tools import cast_vote, get_entity_updates, register_update
from app.shared.ip_privacy import (
    VOTER_COOKIE_NAME,
    get_or_create_voter_token,
    is_terms_accepted,
    verify_voter_token,
)
from app.shared.security import (
    check_create_update_rate_limit,
    check_rate_limit,
    get_client_ip,
    has_voted_recently,
    mark_as_voted,
)

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
    accept_terms: bool = Form(True),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Save community report and return confirmation fragment."""
    if not is_terms_accepted(accept_terms):
        return HTMLResponse(
            content="<div style='background: #FFF1F2; border: 1px solid #FECDD3; border-radius: 8px; padding: 14px; color: #E11D48; font-size: 13px;'><strong>Consentimiento requerido:</strong> Debes aceptar la política de tratamiento de datos personales (Ley 1581 de 2012) para enviar un reporte comunitario.</div>",
            status_code=400,
        )

    client_ip = get_client_ip(request)
    voter_id, new_voter_cookie = get_or_create_voter_token(request)
    # Validate with Pydantic before delegating to tools
    try:
        CommunityUpdateCreate(
            update_type=update_type,
            note=note,
            campaign_id=campaign_id,
            animal_id=animal_id,
        )
        if not await check_create_update_rate_limit(
            client_ip,
            campaign_id=campaign_id,
            animal_id=animal_id,
            window_seconds=900,
            voter_token=voter_id,
        ):
            return HTMLResponse(
                content="<div style='background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 8px; padding: 14px; color: #B45309; font-size: 13px;'><strong>⏳ Límite alcanzado:</strong> Ya enviaste un reporte recientemente para este caso. Espera 15 minutos antes de enviar otro.</div>",
                status_code=429,
            )
        new_update = await register_update(
            db, update_type, note, campaign_id, animal_id
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<div style='background: #FFF1F2; border: 1px solid #FECDD3; border-radius: 8px; padding: 14px; color: #E11D48; font-size: 13px;'><strong>Error de validación:</strong> {e!s}</div>",
            status_code=400,
        )

    # 2. Block the creator from immediate self-voting
    await mark_as_voted(client_ip, new_update.id, voter_token=voter_id)

    # Build confirmation response
    response = templates.TemplateResponse(
        request=request, name="update_confirmation.html", context={}
    )

    response.headers["HX-Trigger"] = "newCommunityUpdate"
    if new_voter_cookie is not None:
        is_secure = getattr(getattr(request, "url", None), "scheme", "http") == "https"
        response.set_cookie(
            key=VOTER_COOKIE_NAME,
            value=new_voter_cookie,
            httponly=True,
            samesite="lax",
            secure=is_secure,
            path="/",
            max_age=86400,
        )

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
    client_ip = get_client_ip(request)
    raw_cookie = (
        request.cookies.get(VOTER_COOKIE_NAME)
        if hasattr(request, "cookies") and request.cookies
        else None
    )
    voter_id = verify_voter_token(raw_cookie)

    # Identify report IDs the actor has already voted for
    voted_ids = [
        u.id
        for u in updates
        if await has_voted_recently(client_ip, u.id, voter_token=voter_id)
    ]

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

    # 1. Retrieve client IP and signed voter cookie token
    client_ip = get_client_ip(request)
    voter_id, new_voter_cookie = get_or_create_voter_token(request)

    # 2. Check rate limit window (900 seconds = 15 minutes) across both network digest & voter token
    if not await check_rate_limit(
        client_ip, update_id, window_seconds=900, voter_token=voter_id
    ):
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

    response = templates.TemplateResponse(
        request=request,
        name="vote_status.html",
        context={
            "update": update_obj,
            "threshold": settings.COMMUNITY_VOTE_THRESHOLD,
            "voted_ids": [update_id],
        },
    )
    if new_voter_cookie is not None:
        is_secure = getattr(getattr(request, "url", None), "scheme", "http") == "https"
        response.set_cookie(
            key=VOTER_COOKIE_NAME,
            value=new_voter_cookie,
            httponly=True,
            samesite="lax",
            secure=is_secure,
            path="/",
            max_age=86400,
        )
    return response
