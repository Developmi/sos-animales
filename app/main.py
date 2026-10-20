"""FastAPI application entrypoint. Mounts StaticFiles and domain routers:

- /sources — registration and verification of shelters and rescuers
- /sterilization — campaigns and fixed sterilization points
- /animals — adoption profiles
- /community — community updates and reports
- /verification — veterinary inspection and auditing workflows
- /auth — administration authentication and dashboard
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, engine
from app.domains.sources.router import router as sources_router
from app.domains.sterilization.router import router as sterilization_router
from app.domains.animals.router import router as animals_router
from app.domains.community.router import router as community_router
from app.domains.verification.router import router as verification_router
from app.domains.auth.router import router as auth_router
from app.shared import cache
from app.shared import geo

# ── Global Logging Configuration ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize Valkey and verify PostgreSQL connection on startup; clean up on shutdown."""
    # 1. Startup: Verify PostgreSQL readiness
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL database connection verified and healthy")
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL on startup: %s", e)

    # 2. Startup: initialize Valkey client via cache module
    valkey_client = cache.init_valkey(settings.VALKEY_URL)
    geo.valkey_client = valkey_client  # keep backwards compatibility with geo module
    app.state.valkey = valkey_client
    try:
        await valkey_client.ping()
        logger.info("Valkey connected and responsive")
    except Exception as e:
        logger.warning(
            "Valkey not reachable on startup (%s); client retained for auto-reconnect",
            e,
        )
    yield
    # Shutdown
    await cache.close_valkey()
    geo.valkey_client = None


app = FastAPI(title="SOS Animales", lifespan=lifespan)

# Reverse proxy header support (X-Forwarded-For) for accurate rate limiting
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1", "100.*"])

app.include_router(sources_router)
app.include_router(sterilization_router)
app.include_router(animals_router)
app.include_router(community_router)
app.include_router(verification_router)
app.include_router(auth_router)

# Template engine configuration
templates = Jinja2Templates(directory="app/shared/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request) -> HTMLResponse:
    """Home landing page."""
    return templates.TemplateResponse(request=request, name="home.html", context={})


# --- SRE Health & Diagnostics Endpoints ---
@app.get("/health/live", tags=["health"])
async def liveness_probe() -> JSONResponse:
    """Liveness probe returning 200 OK when FastAPI event loop is responsive."""
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "alive"})


@app.get("/health/ready", tags=["health"])
async def readiness_probe(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness probe verifying PostgreSQL and Valkey active connectivity."""
    checks: dict[str, str] = {"database": "unknown", "valkey": "unknown"}
    is_ready = True

    # Check PostgreSQL connection
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        checks["database"] = "ok"
    except Exception as e:
        logger.error("Readiness check: PostgreSQL unhealthy: %s", e)
        checks["database"] = f"unhealthy: {type(e).__name__}"
        is_ready = False

    # Check Valkey cache connection
    try:
        if cache.valkey_client is not None:
            await asyncio.wait_for(cache.valkey_client.ping(), timeout=1.0)
            checks["valkey"] = "ok"
        else:
            checks["valkey"] = "degraded (not initialized)"
    except Exception as e:
        logger.warning("Readiness check: Valkey degraded: %s", e)
        checks["valkey"] = f"degraded: {type(e).__name__}"

    http_status = (
        status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(
        status_code=http_status,
        content={"status": "ready" if is_ready else "not_ready", "checks": checks},
    )


# --- HTMX diagnostic test endpoint ---
@app.get("/api/ping-htmx", response_class=HTMLResponse)
async def ping_htmx() -> Response:
    """Return HTML fragment for HTMX ping check."""
    return HTMLResponse(
        "<article><header>¡Éxito!</header>HTMX se comunicó con FastAPI y trajo este fragmento sin recargar la página. 🚀</article>"
    )


@app.get("/legal/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal/privacy_policy.html", {})


@app.get("/legal/cookies", response_class=HTMLResponse)
async def cookies_policy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal/cookies_policy.html", {})


@app.get("/legal/terms", response_class=HTMLResponse)
async def terms_of_use(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal/terms_of_use.html", {})


@app.get("/legal/data-processing", response_class=HTMLResponse)
async def data_processing_consent(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal/data_processing_consent.html", {})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> Response:
    if exc.status_code == 404:
        logger.warning("404 not found: %s %s", request.method, request.url.path)
        return templates.TemplateResponse(
            request, "error_404.html", {"request": request}, status_code=404
        )
    if exc.status_code == 401:
        logger.info(
            "401 unauthorised, redirecting to login: %s %s",
            request.method,
            request.url.path,
        )
        return RedirectResponse(url="/auth/login", status_code=302)

    logger.warning(
        "HTTP %d error on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    if "text/html" in request.headers.get("accept", ""):
        detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error {exc.status_code} | SOS Animales</title>
    <link rel="stylesheet" href="/static/css/sos-animales.css">
</head>
<body>
    <main class="container" style="padding-top: 3rem;">
        <article style="text-align: center;">
            <header><h1>{exc.status_code}</h1><h2>Error</h2></header>
            <p>{detail_msg}</p>
            <a href="/" role="button">← Volver al inicio</a>
        </article>
    </main>
</body>
</html>""",
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
    logger.exception(
        "Unhandled exception on %s %s: %s", request.method, request.url.path, exc
    )
    return templates.TemplateResponse(
        request, "error_500.html", {"request": request}, status_code=500
    )
