"""Tests for email dispatching with SMTP mocking.

Covers:
- send_pin_email_sync: verifies smtplib.SMTP is called with configured parameters.
- send_pin_email_sync without SMTP configured: logs PIN locally without attempting to send.
"""

from unittest.mock import MagicMock, patch

from app.config import settings
from app.shared.email import (
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
