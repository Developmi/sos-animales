"""Comprehensive tests for all application HTTP routers.

Covers auth (login, logout, admin panel), home, ping, legal routes,
and smoke tests for public GET and protected unauthorized routes.
"""

import bcrypt
import jwt
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.config import settings
from app.database import get_db

TEST_ADMIN_PASSWORD = "test_admin_password_123"
TEST_ADMIN_PASSWORD_HASH = bcrypt.hashpw(
    TEST_ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()
).decode("utf-8")


def make_token() -> str:
    return jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


AUTH_COOKIES = {"access_token": make_token()}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies=AUTH_COOKIES,
    ) as ac:
        yield ac


@pytest_asyncio.fixture
def db_override():  # type: ignore[no-untyped-def]
    """Override get_db with a mock that returns safe defaults.

    Routes that query the DB get 0 for scalar() and [] for scalars().all().
    """
    mock = AsyncMock()

    async def fake_execute(stmt: Any) -> MagicMock:
        result = MagicMock()
        result.scalar.return_value = 0
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        return result

    mock.execute = fake_execute

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_auth_login_page(client: AsyncClient) -> None:
    """GET /auth/login must return the login form."""
    response = await client.get("/auth/login")
    assert response.status_code == 200
    assert "Acceso Administrativo" in response.text


@pytest.mark.asyncio
async def test_auth_login_wrong_password(client: AsyncClient) -> None:
    """POST /auth/login with wrong password must return 400."""
    response = await client.post("/auth/login", data={"password": "wrong_password"})
    assert response.status_code == 400
    assert "Contraseña incorrecta" in response.text


@pytest.mark.asyncio
async def test_auth_login_correct_password(client: AsyncClient) -> None:
    """POST /auth/login with correct password must return 302 + cookie."""
    original_hash = settings.ADMIN_PASSWORD_HASH
    settings.ADMIN_PASSWORD_HASH = TEST_ADMIN_PASSWORD_HASH
    try:
        response = await client.post(
            "/auth/login",
            data={"password": TEST_ADMIN_PASSWORD},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/admin/"
        set_cookie = response.headers.get("set-cookie", "")
        assert "access_token=" in set_cookie
        assert "HttpOnly" in set_cookie
    finally:
        settings.ADMIN_PASSWORD_HASH = original_hash


@pytest.mark.asyncio
async def test_auth_login_plain_text_dev_fallback(client: AsyncClient) -> None:
    """POST /auth/login must accept plain text dev fallback if set in env."""
    original_hash = settings.ADMIN_PASSWORD_HASH
    settings.ADMIN_PASSWORD_HASH = "dev_secret_plain"
    try:
        response = await client.post(
            "/auth/login",
            data={"password": "dev_secret_plain"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/admin/"
    finally:
        settings.ADMIN_PASSWORD_HASH = original_hash


@pytest.mark.asyncio
async def test_auth_login_unprefixed_bcrypt_hash(client: AsyncClient) -> None:
    """POST /auth/login must handle bcrypt hash when leading $ was stripped by shell."""
    original_hash = settings.ADMIN_PASSWORD_HASH
    # Strip leading $
    settings.ADMIN_PASSWORD_HASH = TEST_ADMIN_PASSWORD_HASH.lstrip("$")
    try:
        response = await client.post(
            "/auth/login",
            data={"password": TEST_ADMIN_PASSWORD},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/admin/"
    finally:
        settings.ADMIN_PASSWORD_HASH = original_hash


@pytest.mark.asyncio
async def test_auth_logout(client: AsyncClient) -> None:
    """POST /auth/logout must clear the cookie and redirect to /."""
    response = await client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/"
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "Max-Age=0" in set_cookie


@pytest.mark.asyncio
async def test_admin_panel_no_auth(client: AsyncClient) -> None:
    """GET /admin/ without auth must redirect to /auth/login."""
    response = await client.get("/admin/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/auth/login"


@pytest.mark.asyncio
async def test_admin_panel_with_auth(
    auth_client: AsyncClient, db_override: Iterator[None]
) -> None:
    """GET /admin/ with valid token must return 200 with the panel."""
    response = await auth_client.get("/admin/")
    assert response.status_code == 200
    assert "Panel de Administración" in response.text


# ═══════════════════════════════════════════════════════════
# Login rate limiting
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_auth_login_rate_limited(client: AsyncClient) -> None:
    """POST /auth/login when rate-limited must return 429."""
    mock_valkey = AsyncMock()
    mock_valkey.incr = AsyncMock(return_value=6)
    mock_valkey.expire = AsyncMock(return_value=True)

    with patch("app.shared.geo.valkey_client", mock_valkey):
        response = await client.post("/auth/login", data={"password": "any_password"})
    assert response.status_code == 429
    assert "Demasiados intentos" in response.text


@pytest.mark.asyncio
async def test_auth_login_valkey_down(client: AsyncClient) -> None:
    """POST /auth/login when Valkey is unreachable must work (degraded)."""
    mock_valkey = AsyncMock()
    mock_valkey.incr = AsyncMock(side_effect=ConnectionError("Valkey not reachable"))

    original_hash = settings.ADMIN_PASSWORD_HASH
    settings.ADMIN_PASSWORD_HASH = TEST_ADMIN_PASSWORD_HASH
    try:
        with patch("app.shared.geo.valkey_client", mock_valkey):
            response = await client.post(
                "/auth/login",
                data={"password": TEST_ADMIN_PASSWORD},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert response.headers.get("location") == "/admin/"
    finally:
        settings.ADMIN_PASSWORD_HASH = original_hash


@pytest.mark.asyncio
async def test_auth_login_rate_limit_window_expiry(client: AsyncClient) -> None:
    """Rate limit resets after window — first attempt succeeds after being blocked."""
    mock_valkey = AsyncMock()
    mock_valkey.incr = AsyncMock()
    mock_valkey.expire = AsyncMock(return_value=True)

    # First attempt within window → blocked (over limit)
    mock_valkey.incr.side_effect = [6]
    with patch("app.shared.geo.valkey_client", mock_valkey):
        response = await client.post("/auth/login", data={"password": "wrong"})
    assert response.status_code == 429

    # Window "expired" — next INCR resets to 1 → allowed
    mock_valkey.incr.side_effect = [1]
    original_hash = settings.ADMIN_PASSWORD_HASH
    settings.ADMIN_PASSWORD_HASH = TEST_ADMIN_PASSWORD_HASH
    try:
        with patch("app.shared.geo.valkey_client", mock_valkey):
            response = await client.post(
                "/auth/login",
                data={"password": TEST_ADMIN_PASSWORD},
                follow_redirects=False,
            )
        assert response.status_code == 302
    finally:
        settings.ADMIN_PASSWORD_HASH = original_hash


# ═══════════════════════════════════════════════════════════
# Home, Ping, Legal
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_home_page(client: AsyncClient) -> None:
    """GET / must return the landing page."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "SOS Animales" in response.text


@pytest.mark.asyncio
async def test_htmx_ping(client: AsyncClient) -> None:
    """GET /api/ping-htmx must return the HTMX test fragment."""
    response = await client.get("/api/ping-htmx")
    assert response.status_code == 200
    assert "HTMX" in response.text
    assert "FastAPI" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, expected_text",
    [
        ("/legal/privacy", "Privacidad"),
        ("/legal/cookies", "Cookies"),
        ("/legal/terms", "Términos"),
        ("/legal/data-processing", "Datos"),
    ],
)
async def test_legal_routes(client: AsyncClient, path: str, expected_text: str) -> None:
    """All legal-info routes must return 200."""
    response = await client.get(path)
    assert response.status_code == 200
    assert expected_text in response.text


# ═══════════════════════════════════════════════════════════
# Sterilization — public GET routes
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sterilization_search_page(client: AsyncClient) -> None:
    """GET /sterilization/search must return 200 (no DB needed)."""
    response = await client.get("/sterilization/search")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sterilization_new_campaign_form(
    client: AsyncClient, db_override: Iterator[None]
) -> None:
    """GET /sterilization/new must return 200 (needs DB override for sources)."""
    response = await client.get("/sterilization/new")
    assert response.status_code == 200


# ═══════════════════════════════════════════════════════════
# Animals — public GET routes
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_animals_list_page(client: AsyncClient) -> None:
    """GET /animals/ must return 200 (no DB needed)."""
    response = await client.get("/animals/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_animals_new_form(client: AsyncClient) -> None:
    """GET /animals/new must return 200 (no DB needed)."""
    response = await client.get("/animals/new")
    assert response.status_code == 200


# ═══════════════════════════════════════════════════════════
# Sources — public GET routes
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sources_list_page(
    client: AsyncClient, db_override: Iterator[None]
) -> None:
    """GET /sources must return 200 (needs DB override)."""
    response = await client.get("/sources")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sources_register_form(
    client: AsyncClient, db_override: Iterator[None]
) -> None:
    """GET /sources/register must return 200."""
    response = await client.get("/sources/register")
    assert response.status_code == 200


# ═══════════════════════════════════════════════════════════
# Protected POST routes — redirect when no auth cookie
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, form_data",
    [
        (
            "/sterilization/new",
            {
                "title": "x",
                "source_id": "1",
                "municipality": "x",
                "address": "x",
                "starts_at": "2025-01-01T00:00",
                "species": ["canino"],
            },
        ),
        (
            "/sterilization/fixed-points/new",
            {
                "name": "x",
                "source_id": "1",
                "municipality": "x",
                "address": "x",
                "schedule_text": "x",
                "species": ["canino"],
            },
        ),
        (
            "/verification/request",
            {"source_id": "1"},
        ),
    ],
)
async def test_protected_post_routes_redirect_no_auth(
    client: AsyncClient, path: str, form_data: dict[str, str]
) -> None:
    """Protected POST routes without auth → 302 redirect to /auth/login."""
    response = await client.request(
        "POST", path, data=form_data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers.get("location") == "/auth/login"


@pytest.mark.asyncio
async def test_protected_verification_checklist_no_auth(
    client: AsyncClient,
) -> None:
    """POST /verification/visits/{id}/checklist without auth → 302."""
    response = await client.post(
        "/verification/visits/1/checklist",
        data={},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers.get("location") == "/auth/login"


@pytest.mark.asyncio
async def test_admin_verify_source_no_auth(client: AsyncClient) -> None:
    """POST /admin/sources/1/verify without auth → 302 redirect."""
    response = await client.post("/admin/sources/1/verify", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/auth/login"


@pytest.mark.asyncio
async def test_admin_verify_source_with_auth(
    auth_client: AsyncClient, db_override: Iterator[None]
) -> None:
    """POST /admin/sources/1/verify with auth verifies the foundation."""
    response = await auth_client.post("/admin/sources/1/verify")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert "OFICIAL VERIFICADA" in response.text


@pytest.mark.asyncio
async def test_active_municipality_options(
    client: AsyncClient, db_override: Iterator[None]
) -> None:
    """GET /sterilization/active-municipality-options returns active options."""
    response = await client.get("/sterilization/active-municipality-options")
    assert response.status_code == 200
    assert "<option" in response.text
