"""SRE resilience and chaos integration tests.

Covers:
1. Valkey mid-request connection failure tolerance and seamless memory fallback.
2. Adoption PIN rate-limiting resilience during Valkey socket timeouts.
3. R2 storage fail-fast behavior: prevents silently masking production storage failures as placeholders.
4. PostgreSQL statement_timeout enforcement to protect connection pools from hung queries.
5. Readiness endpoint (/health/ready) degraded status reporting without service interruption.
"""

import io
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.animals.tools import upload_photo_to_r2
from app.main import app
from app.shared.security import (
    _pin_attempts,
    _vote_fallback,
    check_pin_rate_limit,
    check_rate_limit,
    record_failed_pin_attempt,
)


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_valkey_mid_request_outage_fallback_in_rate_limit() -> None:
    """If Valkey raises ConnectionError mid-request, check_rate_limit must fall back to in-memory gracefully."""
    mock_valkey = MagicMock()
    mock_valkey.set.side_effect = ConnectionError("Valkey cluster connection dropped")

    test_ip = "192.168.1.99"
    test_update_id = 8888
    # Clear previous fallback state
    _vote_fallback.pop((test_ip, test_update_id), None)

    with patch("app.shared.cache.valkey_client", mock_valkey):
        # First vote should succeed using in-memory fallback
        allowed_1 = await check_rate_limit(test_ip, test_update_id, window_seconds=900)
        assert allowed_1 is True

        # Second vote within window should be blocked by in-memory fallback
        allowed_2 = await check_rate_limit(test_ip, test_update_id, window_seconds=900)
        assert allowed_2 is False


@pytest.mark.asyncio
async def test_valkey_mid_request_outage_fallback_in_pin_rate_limit() -> None:
    """If Valkey raises TimeoutError, PIN rate-limiting must operate using in-memory state."""
    mock_valkey = MagicMock()
    mock_valkey.get.side_effect = TimeoutError("Valkey socket timeout")
    mock_valkey.pipeline.side_effect = TimeoutError("Valkey socket timeout")

    test_ip = "192.168.1.105"
    test_animal_id = 7777
    _pin_attempts.pop((test_ip, test_animal_id), None)

    with patch("app.shared.cache.valkey_client", mock_valkey):
        # Record 5 failed attempts
        for _ in range(5):
            await record_failed_pin_attempt(
                test_ip, test_animal_id, window_seconds=3600
            )

        # Verify that 6th attempt is blocked by the fallback
        can_attempt = await check_pin_rate_limit(
            test_ip, test_animal_id, max_attempts=5, window_seconds=3600
        )
        assert can_attempt is False


@pytest.mark.asyncio
async def test_r2_configured_failure_does_not_silently_mask_as_fake_placeholder() -> (
    None
):
    """If R2_ENDPOINT is configured and upload fails, raise an exception instead of returning silent placeholder."""
    mock_s3 = MagicMock()
    mock_s3.upload_fileobj.side_effect = RuntimeError(
        "S3 Network Failure / AccessDenied"
    )

    fake_file = UploadFile(
        file=io.BytesIO(b"image bytes"),
        filename="foto_critica.jpg",
    )

    with (
        patch(
            "app.domains.animals.tools.settings.R2_ENDPOINT",
            "https://r2.production.cloud",
        ),
        patch("app.domains.animals.tools.settings.R2_ACCESS_KEY_ID", "real_key"),
        patch("app.domains.animals.tools.settings.R2_SECRET_ACCESS_KEY", "real_secret"),
        patch("app.domains.animals.tools.settings.R2_BUCKET_NAME", "real_bucket"),
        patch("boto3.client", return_value=mock_s3),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await upload_photo_to_r2(fake_file)

        assert (
            "S3 Network Failure" in str(exc_info.value)
            or "r2" in str(exc_info.value).lower()
        )


@pytest.mark.asyncio
async def test_database_statement_timeout_cancels_runaway_queries(
    db_session: AsyncSession,
) -> None:
    """Validate that configured statement_timeout cancels queries that exceed execution time limits."""
    # Set ultra-short timeout on session (100ms) and simulate slow query (300ms)
    await db_session.execute(text("SET statement_timeout = 100"))

    with pytest.raises(Exception) as exc_info:
        await db_session.execute(text("SELECT pg_sleep(0.3)"))

    # Must be canceled by PostgreSQL
    error_msg = str(exc_info.value).lower()
    assert (
        "canceling statement due to statement timeout" in error_msg
        or "statement_timeout" in error_msg
        or "querycancelederror" in error_msg
    )

    # Rollback session to restore clean state
    await db_session.rollback()


@pytest.mark.asyncio
async def test_health_ready_reports_degraded_when_valkey_down_without_crashing(
    app_client: AsyncClient,
) -> None:
    """When Valkey is unreachable, /health/ready should report degraded status in 200 payload without 500 crashes."""
    with patch("app.shared.cache.valkey_client") as mock_valkey:
        mock_valkey.ping.side_effect = ConnectionError("Valkey is down")

        response = await app_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "degraded" in data["checks"]["valkey"]
        assert data["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_valkey_outage_login_rate_limit_memory_fallback() -> None:
    """When Valkey is unreachable, check_login_rate_limit must enforce in-memory rate limiting."""
    from app.domains.auth.rate_limit import _login_fallback, check_login_rate_limit

    test_ip = "10.0.0.99"
    _login_fallback.pop(test_ip, None)

    mock_valkey = MagicMock()
    mock_valkey.incr.side_effect = ConnectionError("Valkey offline")

    with patch("app.shared.cache.valkey_client", mock_valkey):
        # First 5 attempts within window must be allowed
        for _ in range(5):
            allowed = await check_login_rate_limit(test_ip)
            assert allowed is True

        # 6th attempt must be blocked by the in-memory fallback
        blocked = await check_login_rate_limit(test_ip)
        assert blocked is False

        # Different IP should still have its own quota
        other_ip_allowed = await check_login_rate_limit("10.0.0.100")
        assert other_ip_allowed is True
