import hmac
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.animals.models import AnimalProfile
from app.domains.auth import rate_limit
from app.domains.auth.middleware import require_auth
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign, FixedPoint

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
    client_ip = request.client.host if request.client else "127.0.0.1"
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
        },
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
