"""Tests for email dispatching with SMTP mocking.

Covers:
- send_pin_email_sync: verifies smtplib.SMTP is called with configured parameters.
- send_pin_email_sync without SMTP configured: logs PIN locally without attempting to send.
"""

from unittest.mock import MagicMock, patch

import httpx

from app.config import settings
from app.shared.email import (
    ResendEmailProvider,
    SmtpEmailProvider,
    get_email_provider,
    send_pin_email_sync,
)
from app.shared.email import (
    test_smtp_connection as run_smtp_diagnostic,
)

# ── TC-01: Email dispatch with mocked SMTP ───────────────────────────────────


@patch("app.shared.email.smtplib.SMTP")
def test_send_pin_email_sync_calls_smtp(mock_smtp: MagicMock) -> None:
    """send_pin_email_sync must invoke smtplib.SMTP with configured credentials and timeout."""
    # Force SMTP credentials so the function executes completely
    with (
        patch.object(settings, "SMTP_USER", "test@ejemplo.com"),
        patch.object(settings, "SMTP_PASSWORD", "secret"),
    ):
        send_pin_email_sync("test@ejemplo.com", "Refugio Test", "1234")

    # Verify SMTP client creation with host, port, and security timeout
    mock_smtp.assert_called_once_with(
        settings.SMTP_HOST, settings.SMTP_PORT, timeout=10
    )

    # Context manager uses __enter__ to obtain server instance
    server = mock_smtp.return_value.__enter__.return_value

    # Verify starttls and login calls
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("test@ejemplo.com", "secret")

    # Verify message dispatch
    server.send_message.assert_called_once()

    # Verify message payload
    msg = server.send_message.call_args[0][0]
    assert msg["To"] == "test@ejemplo.com"
    assert msg["Subject"] == "Tu PIN de administración para: Refugio Test"
    assert "1234" in msg.get_content()


# ── TC-02: Unconfigured SMTP ────────────────────────────────────────────────


@patch("app.shared.email.smtplib.SMTP")
def test_send_pin_email_sync_smtp_not_configured(mock_smtp: MagicMock) -> None:
    """When SMTP credentials are missing, it must not attempt to connect or send."""
    with (
        patch.object(settings, "SMTP_USER", None),
        patch.object(settings, "SMTP_PASSWORD", None),
    ):
        send_pin_email_sync("test@ejemplo.com", "Test", "5678")

    mock_smtp.assert_not_called()


# ── TC-03: PIN inclusion in email body ──────────────────────────────────────


@patch("app.shared.email.smtplib.SMTP")
def test_send_pin_email_sync_contains_pin_in_body(mock_smtp: MagicMock) -> None:
    """Email body must contain the plaintext PIN code."""
    with (
        patch.object(settings, "SMTP_USER", "user@test.com"),
        patch.object(settings, "SMTP_PASSWORD", "pass"),
    ):
        send_pin_email_sync("alguien@ejemplo.com", "Mi Entidad", "4821")

    server = mock_smtp.return_value.__enter__.return_value
    msg = server.send_message.call_args[0][0]
    body = msg.get_content()

    assert "4821" in body
    assert "Mi Entidad" in body


# ── TC-04: Port 465 SSL Support ─────────────────────────────────────────────


@patch("app.shared.email.smtplib.SMTP_SSL")
def test_send_pin_email_sync_port_465_uses_smtp_ssl(
    mock_smtp_ssl: MagicMock,
) -> None:
    """Port 465 must use smtplib.SMTP_SSL with timeout."""
    with (
        patch.object(settings, "SMTP_USER", "user@test.com"),
        patch.object(settings, "SMTP_PASSWORD", "pass"),
        patch.object(settings, "SMTP_PORT", 465),
    ):
        send_pin_email_sync("alguien@ejemplo.com", "SSL Test", "9999")

    mock_smtp_ssl.assert_called_once_with(settings.SMTP_HOST, 465, timeout=10)
    server = mock_smtp_ssl.return_value.__enter__.return_value
    server.login.assert_called_once_with("user@test.com", "pass")
    server.send_message.assert_called_once()


# ── TC-05: Diagnostic helper test_smtp_connection ──────────────────────────


@patch("app.shared.email.smtplib.SMTP")
def test_test_smtp_connection_success(mock_smtp: MagicMock) -> None:
    """test_smtp_connection returns success True when server responds."""
    with (
        patch.object(settings, "SMTP_USER", "user@test.com"),
        patch.object(settings, "SMTP_PASSWORD", "pass"),
        patch.object(settings, "SMTP_PORT", 587),
    ):
        ok, msg = run_smtp_diagnostic("dest@ejemplo.com")

    assert ok is True
    assert (
        "exitosa" in msg.lower() or "éxito" in msg.lower() or "success" in msg.lower()
    )


@patch("app.shared.email.smtplib.SMTP")
def test_test_smtp_connection_failure_handles_gracefully(
    mock_smtp: MagicMock,
) -> None:
    """test_smtp_connection returns False and descriptive error on network/auth failure."""
    mock_smtp.side_effect = TimeoutError("Connection timed out")
    with (
        patch.object(settings, "SMTP_USER", "user@test.com"),
        patch.object(settings, "SMTP_PASSWORD", "pass"),
        patch.object(settings, "SMTP_PORT", 587),
    ):
        ok, msg = run_smtp_diagnostic("dest@ejemplo.com")

    assert ok is False
    assert (
        "timeout" in msg.lower() or "timed out" in msg.lower() or "error" in msg.lower()
    )


# ── TC-06: Resend Email Provider ─────────────────────────────────────────────


@patch("app.shared.email.httpx.Client")
def test_resend_send_pin_email_success(mock_client_cls: MagicMock) -> None:
    """ResendEmailProvider dispatches JSON payload over HTTPS with Bearer token."""
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client.post.return_value = mock_response

    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_test_123456789"),
        patch.object(settings, "FROM_EMAIL", "onboarding@resend.dev"),
    ):
        result = send_pin_email_sync("user@example.com", "Mascota Perdida", "4321")

    assert result is True
    mock_client.post.assert_called_once()
    url, kwargs = mock_client.post.call_args
    assert url[0] == "https://api.resend.com/emails"
    assert kwargs["headers"]["Authorization"] == "Bearer re_test_123456789"
    assert kwargs["json"]["to"] == ["user@example.com"]
    assert kwargs["json"]["from"] == "onboarding@resend.dev"
    assert "4321" in kwargs["json"]["text"]


def test_resend_send_pin_email_unconfigured() -> None:
    """ResendEmailProvider simulates delivery and returns False when API key is missing."""
    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", None),
        patch.object(settings, "SMTP_PASSWORD", ""),
    ):
        result = send_pin_email_sync("user@example.com", "Mascota", "1111")

    assert result is False


@patch("app.shared.email.httpx.Client")
def test_resend_send_pin_email_api_error(mock_client_cls: MagicMock) -> None:
    """ResendEmailProvider returns False when API returns HTTP 422 or 401."""
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_response = MagicMock()
    mock_response.status_code = 422
    mock_response.text = '{"message": "Domain not verified"}'
    mock_client.post.return_value = mock_response

    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_test_key"),
    ):
        result = send_pin_email_sync("user@example.com", "Mascota", "1111")

    assert result is False


@patch("app.shared.email.httpx.Client")
def test_resend_send_pin_email_network_exception(mock_client_cls: MagicMock) -> None:
    """ResendEmailProvider returns False when connection raises an exception."""
    mock_client = mock_client_cls.return_value.__enter__.return_value
    mock_client.post.side_effect = httpx.ConnectTimeout("Connection timed out")

    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_test_key"),
    ):
        result = send_pin_email_sync("user@example.com", "Mascota", "1111")

    assert result is False


def test_resend_api_key_fallback_to_smtp_password() -> None:
    """When RESEND_API_KEY is not set, ResendEmailProvider falls back to SMTP_PASSWORD if starting with re_."""
    provider = ResendEmailProvider()
    with (
        patch.object(settings, "RESEND_API_KEY", None),
        patch.object(settings, "SMTP_PASSWORD", "re_fallback_key"),
    ):
        assert provider.api_key == "re_fallback_key"

    with (
        patch.object(settings, "RESEND_API_KEY", None),
        patch.object(settings, "SMTP_PASSWORD", "regular_smtp_password"),
    ):
        assert provider.api_key == ""


@patch("app.shared.email.httpx.Client")
def test_resend_test_connection_diagnostics(mock_client_cls: MagicMock) -> None:
    """Verify test_connection diagnostics with and without to_email."""
    mock_client = mock_client_cls.return_value.__enter__.return_value

    # Case 1: unconfigured API key
    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", None),
        patch.object(settings, "SMTP_PASSWORD", ""),
    ):
        ok, msg = run_smtp_diagnostic()
        assert ok is False
        assert "RESEND_API_KEY" in msg

    # Case 2: validate API keys (to_email is None) - 200 OK
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_client.get.return_value = mock_resp_200
    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_valid_key"),
        patch.object(settings, "FROM_EMAIL", "onboarding@resend.dev"),
    ):
        ok, msg = run_smtp_diagnostic()
        assert ok is True
        assert "exitosa" in msg.lower() or "443" in msg

    # Case 3: validate API keys (to_email is None) - 401 Unauthorized
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401
    mock_client.get.return_value = mock_resp_401
    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_invalid_key"),
        patch.object(settings, "FROM_EMAIL", "onboarding@resend.dev"),
    ):
        ok, msg = run_smtp_diagnostic()
        assert ok is False
        assert "inválida" in msg.lower() or "autenticación" in msg.lower()

    # Case 4: send test email (to_email provided) - 200 OK
    mock_client.post.return_value = mock_resp_200
    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_valid_key"),
        patch.object(settings, "FROM_EMAIL", "onboarding@resend.dev"),
    ):
        ok, msg = run_smtp_diagnostic("admin@developmi.com")
        assert ok is True
        assert "admin@developmi.com" in msg

    # Case 5: timeout exception
    mock_client.get.side_effect = httpx.TimeoutException("Read timed out")
    with (
        patch.object(settings, "EMAIL_PROVIDER", "resend"),
        patch.object(settings, "RESEND_API_KEY", "re_valid_key"),
        patch.object(settings, "FROM_EMAIL", "onboarding@resend.dev"),
    ):
        ok, msg = run_smtp_diagnostic()
        assert ok is False
        assert "timeout" in msg.lower()


def test_get_email_provider_factory() -> None:
    """get_email_provider returns correct provider instance according to settings."""
    with patch.object(settings, "EMAIL_PROVIDER", "resend"):
        assert isinstance(get_email_provider(), ResendEmailProvider)

    with patch.object(settings, "EMAIL_PROVIDER", "smtp"):
        assert isinstance(get_email_provider(), SmtpEmailProvider)

    with patch.object(settings, "EMAIL_PROVIDER", "unknown_fallback"):
        assert isinstance(get_email_provider(), SmtpEmailProvider)
