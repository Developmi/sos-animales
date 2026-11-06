import hmac
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.animals.models import AnimalProfile
from app.domains.auth import rate_limit
from app.domains.auth.middleware import require_auth
from app.domains.community.models import CommunityUpdate
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign, FixedPoint
from app.shared import maintenance
from app.shared.security import get_client_ip

router = APIRouter(tags=["auth"])

templates = Jinja2Templates(
    directory=["app/domains/auth/templates", "app/shared/templates"]
)
templates.env.globals["settings"] = settings


@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/admin/login")
async def admin_login_redirect() -> RedirectResponse:
    """Defensive redirect for requests to /admin/login towards official /auth/login."""
    return RedirectResponse(url="/auth/login", status_code=302)


def verify_admin_password(plain_password: str, stored_hash_or_plain: str) -> bool:
    """Verifies plain password against stored hash or raw dev fallback in constant time."""
    stored = stored_hash_or_plain.strip().strip("'\"")
    if (
        stored.startswith("$2")
        or stored.startswith("2b$")
        or stored.startswith("2a$")
        or stored.startswith("2y$")
    ):
        if not stored.startswith("$"):
            stored = "$" + stored
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), stored.encode("utf-8")
            )
        except (ValueError, TypeError):
            pass
    # Constant-time comparison for raw plain text fallback (dev convenience)
    return hmac.compare_digest(plain_password, stored)


@router.post("/auth/login", response_class=HTMLResponse)
async def login(request: Request, password: str = Form(...)) -> Response:
    client_ip = get_client_ip(request)
    if not await rate_limit.check_login_rate_limit(client_ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Demasiados intentos. Espera un minuto."},
            status_code=429,
        )
    if not verify_admin_password(password, settings.ADMIN_PASSWORD_HASH):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Contraseña incorrecta"},
            status_code=400,
        )
    exp = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": "admin", "exp": exp}, settings.JWT_SECRET, algorithm="HS256"
    )
    response = RedirectResponse(url="/admin/", status_code=302)
    is_secure = request.url.scheme == "https"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )
    return response


@router.post("/auth/logout", response_class=HTMLResponse)
async def logout(request: Request) -> Response:
    response = RedirectResponse(url="/", status_code=302)
    is_secure = request.url.scheme == "https"
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
        max_age=0,
    )
    return response


@router.get("/admin/", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    campaign_count = (await db.execute(select(func.count(Campaign.id)))).scalar() or 0
    animal_count = (
        await db.execute(select(func.count(AnimalProfile.id)))
    ).scalar() or 0
    source_count = (await db.execute(select(func.count(Source.id)))).scalar() or 0
    fixed_point_count = (
        await db.execute(select(func.count(FixedPoint.id)))
    ).scalar() or 0

    sources_res = await db.execute(select(Source).order_by(Source.created_at.desc()))
    all_sources = sources_res.scalars().all()
    pending_sources = [s for s in all_sources if s.status == "pending"]
    verified_sources = [s for s in all_sources if s.status == "verified"]

    maintenance_info = await maintenance.get_maintenance_info()

    return templates.TemplateResponse(
        request,
        "admin_panel.html",
        {
            "campaign_count": campaign_count,
            "animal_count": animal_count,
            "source_count": source_count,
            "fixed_point_count": fixed_point_count,
            "pending_sources": pending_sources,
            "verified_sources": verified_sources,
            "maintenance_info": maintenance_info,
        },
    )


@router.post("/admin/maintenance/toggle", response_class=HTMLResponse)
async def admin_toggle_maintenance(
    request: Request,
    _: None = Depends(require_auth),
) -> HTMLResponse:
    """Toggles maintenance mode status and returns updated HTMX component."""
    current_active = await maintenance.is_maintenance_active()
    new_active = not current_active
    reason = (
        "Pausa preventiva activada desde el panel administrativo" if new_active else ""
    )
    await maintenance.set_maintenance_mode(new_active, reason=reason)

    maintenance_info = await maintenance.get_maintenance_info()
    return templates.TemplateResponse(
        request,
        "maintenance_card.html",
        {"maintenance_info": maintenance_info},
    )


@router.post("/admin/sources/{source_id}/verify", response_class=HTMLResponse)
async def admin_verify_source(
    request: Request,
    source_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    from app.domains.sources.tools import verify_source

    source = await verify_source(db, source_id)
    if not source:
        return HTMLResponse(
            "<span style='color: var(--color-danger);'>Fundación no encontrada</span>",
            status_code=404,
        )
    return HTMLResponse(
        f"""
        <div id="source-row-{source.id}" style="padding: 14px 18px; background: rgba(13, 148, 136, 0.08); border: 1px solid var(--color-teal-border); border-left: 4px solid var(--color-teal); border-radius: 10px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div>
            <div style="font-weight: 700; color: var(--color-text-main); font-size: 15px;">{source.name}</div>
            <div style="font-size: 13px; color: var(--color-text-secondary); margin-top: 2px;">
              📍 {source.municipality.capitalize()} • Tipo: {source.type.capitalize()}
            </div>
            <div style="font-size: 12px; color: var(--color-teal); font-weight: 700; margin-top: 4px;">
              ✓ Verificada exitosamente por el Administrador
            </div>
          </div>
          <span class="brand-badge" style="background: rgba(13, 148, 136, 0.15); color: var(--color-teal); border: 1px solid var(--color-teal); border-radius: 9999px; padding: 4px 14px; font-weight: 700; font-size: 12px;">
            OFICIAL VERIFICADA
          </span>
        </div>
        """
    )


# ── Admin CRUD: Sources ──────────────────────────────────────────────────────


@router.get("/admin/sources", response_class=HTMLResponse)
async def admin_sources_list(
    request: Request,
    status_filter: str = Query("all"),
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    stmt = select(Source).order_by(Source.created_at.desc())
    if status_filter == "active":
        stmt = stmt.where(Source.is_active.is_(True))
    elif status_filter == "inactive":
        stmt = stmt.where(Source.is_active.is_(False))
    sources_res = await db.execute(stmt)
    sources = sources_res.scalars().all()
    return templates.TemplateResponse(
        request,
        "admin_sources.html",
        {"sources": sources, "status_filter": status_filter},
    )


@router.get("/admin/sources/{source_id}/edit", response_class=HTMLResponse)
async def admin_get_source_edit(
    request: Request,
    source_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    source = (
        await db.execute(select(Source).where(Source.id == source_id))
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fundación no encontrada")
    return templates.TemplateResponse(
        request, "admin_source_edit.html", {"source": source}
    )


@router.post("/admin/sources/{source_id}/edit")
async def admin_post_source_edit(
    request: Request,
    source_id: int,
    name: str = Form(...),
    type: str = Form(...),
    municipality: str = Form(...),
    department: str = Form(...),
    contact_email: str | None = Form(None),
    contact_whatsapp: str | None = Form(None),
    status: str = Form("pending"),
    is_active: bool = Form(False),
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    source = (
        await db.execute(select(Source).where(Source.id == source_id))
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fundación no encontrada")
    source.name = name
    source.type = type
    source.municipality = municipality
    source.department = department
    source.contact_email = contact_email or None
    source.contact_whatsapp = contact_whatsapp or None
    source.status = status
    source.is_active = is_active
    await db.commit()
    await db.refresh(source)
    return RedirectResponse(url="/admin/sources", status_code=303)


@router.post("/admin/sources/{source_id}/delete")
async def admin_post_source_delete(
    request: Request,
    source_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    source = (
        await db.execute(select(Source).where(Source.id == source_id))
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fundación no encontrada")
    source.is_active = False
    source.status = "inactive"
    await db.commit()
    if "HX-Request" in request.headers:
        return HTMLResponse(
            f"<div class='alert-box' style='padding: 12px; background: #FFF1F2; color: #BE123C; border-radius: 8px;'>Organización '{source.name}' desactivada.</div>"
        )
    return RedirectResponse(url="/admin/sources", status_code=303)


@router.post("/admin/sources/{source_id}/reactivate")
async def admin_post_source_reactivate(
    request: Request,
    source_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Reactivate an inactive foundation/shelter."""
    source = (
        await db.execute(select(Source).where(Source.id == source_id))
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Fundación no encontrada")
    source.is_active = True
    source.status = "verified"
    await db.commit()
    if "HX-Request" in request.headers:
        return HTMLResponse(
            f"<div class='alert-box' style='padding: 12px; background: #ECFDF5; color: #047857; border-radius: 8px;'>Organización '{source.name}' reactivada exitosamente.</div>"
        )
    return RedirectResponse(url="/admin/sources", status_code=303)


# ── Admin CRUD: Sterilizations ───────────────────────────────────────────────


@router.get("/admin/sterilizations", response_class=HTMLResponse)
async def admin_sterilizations_list(
    request: Request,
    status_filter: str = Query("all"),
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    stmt = select(Campaign).order_by(Campaign.starts_at.desc())
    if status_filter == "scheduled":
        stmt = stmt.where(Campaign.status == "scheduled")
    elif status_filter == "cancelled":
        stmt = stmt.where(Campaign.status == "cancelled")
    camps_res = await db.execute(stmt)
    campaigns = camps_res.scalars().all()
    return templates.TemplateResponse(
        request,
        "admin_sterilizations.html",
        {"campaigns": campaigns, "status_filter": status_filter},
    )
    return templates.TemplateResponse(
        request, "admin_sterilizations.html", {"campaigns": campaigns}
    )


@router.get(
    "/admin/sterilizations/campaigns/{campaign_id}/edit", response_class=HTMLResponse
)
async def admin_get_campaign_edit(
    request: Request,
    campaign_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    camp = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    return templates.TemplateResponse(
        request, "admin_campaign_edit.html", {"campaign": camp}
    )


@router.post("/admin/sterilizations/campaigns/{campaign_id}/edit")
async def admin_post_campaign_edit(
    request: Request,
    campaign_id: int,
    title: str = Form(...),
    address: str | None = Form(None),
    capacity: int | None = Form(None),
    requirements: str | None = Form(None),
    status: str = Form("scheduled"),
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    camp = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    camp.title = title
    camp.address = address
    camp.capacity = capacity
    camp.requirements = requirements
    camp.status = status
    await db.commit()
    await db.refresh(camp)
    return RedirectResponse(url="/admin/sterilizations", status_code=303)


@router.post("/admin/sterilizations/campaigns/{campaign_id}/delete")
async def admin_post_campaign_delete(
    request: Request,
    campaign_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    camp = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    camp.status = "cancelled"
    await db.commit()
    if "HX-Request" in request.headers:
        return HTMLResponse(
            f"<div class='alert-box' style='padding: 12px; background: #FFF1F2; color: #BE123C; border-radius: 8px;'>Jornada '{camp.title}' cancelada.</div>"
        )
    return RedirectResponse(url="/admin/sterilizations", status_code=303)


@router.post("/admin/sterilizations/campaigns/{campaign_id}/reactivate")
async def admin_post_campaign_reactivate(
    request: Request,
    campaign_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Reactivate a cancelled sterilization campaign."""
    camp = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    camp.status = "scheduled"
    await db.commit()
    if "HX-Request" in request.headers:
        return HTMLResponse(
            f"<div class='alert-box' style='padding: 12px; background: #ECFDF5; color: #047857; border-radius: 8px;'>Jornada '{camp.title}' reactivada como programada.</div>"
        )
    return RedirectResponse(url="/admin/sterilizations", status_code=303)


# ── Admin CRUD: Animals ─────────────────────────────────────────────────────


@router.get("/admin/animals", response_class=HTMLResponse)
async def admin_animals_list(
    request: Request,
    status_filter: str = Query("all"),
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    stmt = select(AnimalProfile).order_by(AnimalProfile.created_at.desc())
    if status_filter != "all":
        stmt = stmt.where(AnimalProfile.status == status_filter)
    animals_res = await db.execute(stmt)
    animals = animals_res.scalars().all()
    return templates.TemplateResponse(
        request,
        "admin_animals.html",
        {"animals": animals, "status_filter": status_filter},
    )


@router.get("/admin/animals/{animal_id}/edit", response_class=HTMLResponse)
async def admin_get_animal_edit(
    request: Request,
    animal_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    animal = (
        await db.execute(select(AnimalProfile).where(AnimalProfile.id == animal_id))
    ).scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Peludo no encontrado")
    return templates.TemplateResponse(
        request, "admin_animal_edit.html", {"animal": animal}
    )


@router.post("/admin/animals/{animal_id}/edit")
async def admin_post_animal_edit(
    request: Request,
    animal_id: int,
    name: str = Form(...),
    species: str = Form(...),
    municipality: str = Form(...),
    age_years: int | None = Form(None),
    status: str = Form("available"),
    is_sterilized: bool = Form(False),
    description: str | None = Form(None),
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    animal = (
        await db.execute(select(AnimalProfile).where(AnimalProfile.id == animal_id))
    ).scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Peludo no encontrado")
    animal.name = name
    animal.species = species
    animal.municipality = municipality
    animal.age_years = age_years
    animal.status = status
    animal.is_sterilized = is_sterilized
    animal.description = description
    await db.commit()
    await db.refresh(animal)
    return RedirectResponse(url="/admin/animals", status_code=303)


@router.post("/admin/animals/{animal_id}/delete")
async def admin_post_animal_delete(
    request: Request,
    animal_id: int,
    _: None = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    animal = (
        await db.execute(select(AnimalProfile).where(AnimalProfile.id == animal_id))
    ).scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Peludo no encontrado")

    # Clean foreign key references in community reports before hard delete
    await db.execute(
        delete(CommunityUpdate).where(CommunityUpdate.animal_id == animal_id)
    )
    await db.delete(animal)
    await db.commit()
    if "HX-Request" in request.headers:
        return HTMLResponse(
            f"<div class='alert-box' style='padding: 12px; background: #FFF1F2; color: #BE123C; border-radius: 8px;'>Perfil de '{animal.name}' eliminado.</div>"
        )
    return RedirectResponse(url="/admin/animals", status_code=303)
