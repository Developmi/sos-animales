from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.domains.auth.middleware import require_auth
from app.domains.auth import rate_limit
from app.domains.sterilization.models import Campaign, FixedPoint
from app.domains.animals.models import AnimalProfile
from app.domains.sources.models import Source

router = APIRouter(tags=["auth"])

templates = Jinja2Templates(
    directory=["app/domains/auth/templates", "app/shared/templates"]
)


@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


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
    if not bcrypt.checkpw(
        password.encode("utf-8"), settings.ADMIN_PASSWORD_HASH.encode("utf-8")
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Contraseña incorrecta"},
            status_code=400,
        )
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
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
    return templates.TemplateResponse(
        request,
        "admin_panel.html",
        {
            "campaign_count": campaign_count,
            "animal_count": animal_count,
            "source_count": source_count,
            "fixed_point_count": fixed_point_count,
        },
    )
