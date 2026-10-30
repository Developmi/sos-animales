from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.shared import maintenance


@pytest.fixture(autouse=True)
def clean_maintenance_state(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Ensure clean maintenance state before each test."""
    flag_file = Path("/tmp/sos_maintenance.flag")
    if flag_file.exists():
        try:
            flag_file.unlink()
        except OSError:
            pass

    # Reset in-memory flag or mock
    yield

    if flag_file.exists():
        try:
            flag_file.unlink()
        except OSError:
            pass


@pytest.mark.asyncio
async def test_maintenance_flag_file_fallback() -> None:
    """Verify fallback to local sentinel file when Valkey client is None."""
    with patch("app.shared.cache.valkey_client", None):
        # Initial state should be inactive
        assert await maintenance.is_maintenance_active() is False

        # Enable maintenance via fallback
        success = await maintenance.set_maintenance_mode(True, reason="Traffic spike")
        assert success is True
        assert await maintenance.is_maintenance_active() is True

        info = await maintenance.get_maintenance_info()
        assert info["active"] is True
        assert info["source"] == "file"

        # Disable maintenance via fallback
        success = await maintenance.set_maintenance_mode(False)
        assert success is True
        assert await maintenance.is_maintenance_active() is False


@pytest.mark.asyncio
async def test_maintenance_valkey_storage() -> None:
    """Verify state management using Valkey when available."""
    mock_valkey = AsyncMock()
    mock_valkey.get.return_value = "1"
    mock_valkey.set.return_value = True

    with patch("app.shared.cache.valkey_client", mock_valkey):
        assert await maintenance.is_maintenance_active() is True
        mock_valkey.get.assert_called_with("sos_animales:maintenance_mode")

        await maintenance.set_maintenance_mode(False)
        mock_valkey.set.assert_called_with("sos_animales:maintenance_mode", "0")


@pytest.mark.asyncio
async def test_cli_maintenance_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify CLI interface for on, off, and status."""
    from app.cli import main as cli_main

    with patch("app.shared.cache.valkey_client", None):
        # 1. Check initial status
        ret = await cli_main(["maintenance", "status"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "INACTIVO" in captured.out or "INACTIVE" in captured.out

        # 2. Turn ON
        ret = await cli_main(["maintenance", "on", "--reason", "Emergency scaling"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "ACTIVADO" in captured.out or "ENABLED" in captured.out
        assert await maintenance.is_maintenance_active() is True

        # 3. Check status when ON
        ret = await cli_main(["maintenance", "status"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "ACTIVO" in captured.out or "ACTIVE" in captured.out

        # 4. Turn OFF
        ret = await cli_main(["maintenance", "off"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "DESACTIVADO" in captured.out or "DISABLED" in captured.out
        assert await maintenance.is_maintenance_active() is False


@pytest.mark.asyncio
async def test_middleware_allows_traffic_when_inactive() -> None:
    """When maintenance is inactive, normal routes respond normally."""
    with patch(
        "app.shared.maintenance.is_maintenance_active", AsyncMock(return_value=False)
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_blocks_public_html_with_503() -> None:
    """When maintenance is active, HTML requests receive HTTP 503 with warm maintenance page."""
    with patch(
        "app.shared.maintenance.is_maintenance_active", AsyncMock(return_value=True)
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/", headers={"Accept": "text/html,application/xhtml+xml"}
            )
            assert response.status_code == 503
            assert response.headers.get("retry-after") == "300"
            assert (
                "pausa" in response.text.lower()
                or "mantenimiento" in response.text.lower()
            )


@pytest.mark.asyncio
async def test_middleware_blocks_public_json_with_503() -> None:
    """When maintenance is active, JSON requests receive HTTP 503 with JSON payload."""
    with patch(
        "app.shared.maintenance.is_maintenance_active", AsyncMock(return_value=True)
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/ping-htmx", headers={"Accept": "application/json"}
            )
            assert response.status_code == 503
            assert response.headers.get("retry-after") == "300"
            data = response.json()
            assert data.get("retry_after") == 300


@pytest.mark.asyncio
async def test_middleware_exempts_health_and_admin_routes() -> None:
    """Health checks and admin panel must always bypass maintenance mode."""
    with patch(
        "app.shared.maintenance.is_maintenance_active", AsyncMock(return_value=True)
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health liveness probe
            live_res = await client.get("/health/live")
            assert live_res.status_code == 200

            # 2. Auth login page
            login_res = await client.get("/auth/login")
            assert login_res.status_code == 200

            # 3. Static assets
            static_res = await client.get("/static/css/sos-animales.css")
            assert static_res.status_code in (200, 304)


@pytest.mark.asyncio
async def test_admin_toggle_maintenance_requires_auth() -> None:
    """Unauthenticated requests to toggle maintenance must be redirected or rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/admin/maintenance/toggle")
        # require_auth raises HTTPException 401 or redirects to /auth/login
        assert res.status_code in (401, 302, 307)


@pytest.mark.asyncio
async def test_admin_toggle_maintenance_success_with_auth() -> None:
    """Authenticated admin can toggle maintenance state via POST."""
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.config import settings

    token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(UTC) + timedelta(minutes=10)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    with patch("app.shared.cache.valkey_client", None):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"access_token": token},
        ) as client:
            # Initially inactive -> toggle to active
            assert await maintenance.is_maintenance_active() is False
            res = await client.post("/admin/maintenance/toggle")
            assert res.status_code == 200
            assert "Modo Mantenimiento Activado" in res.text
            assert await maintenance.is_maintenance_active() is True

            # Toggle back to inactive
            res2 = await client.post("/admin/maintenance/toggle")
            assert res2.status_code == 200
            assert "Portal Público en Línea" in res2.text
            assert await maintenance.is_maintenance_active() is False
