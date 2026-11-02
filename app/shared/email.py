import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _get_smtp_client(timeout: int = 10) -> smtplib.SMTP:
    """Instantiate appropriate SMTP or SMTP_SSL client with security defaults and timeout."""
    if settings.SMTP_PORT == 465:
        return smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout)
    return smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout)


def _prepare_and_login(server: smtplib.SMTP) -> None:
    """Execute STARTTLS if applicable and authenticate."""
    if settings.SMTP_PORT == 587:
        server.starttls()
    elif (
        settings.SMTP_PORT != 465
        and hasattr(server, "has_extn")
        and server.has_extn("STARTTLS")
    ):
        server.starttls()
    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)


def send_pin_email_sync(to_email: str, entity_name: str, pin: str) -> bool:
    """Synchronous function to send management PIN email in background task.

    Sanitizes logging to comply with CWE-532 (no plaintext secrets in logs).
    Returns True if sent successfully, False otherwise.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            "SMTP not configured. Management PIN delivery simulated for: %s (redacted)",
            to_email,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Tu PIN de administración para: {entity_name}"
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email

    content = f"""Hello,

Your publication '{entity_name}' has been created successfully.

Your 4-digit security PIN is: {pin}

Please save this PIN securely. You will need it to update the status (e.g., mark as adopted, full, or cancelled).

Thank you for using SOS Animales.
"""
    msg.set_content(content)

    try:
        with _get_smtp_client(timeout=10) as server:
            _prepare_and_login(server)
            server.send_message(msg)
        logger.info("Management PIN successfully sent to: %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send management PIN to %s: %s", to_email, e)
        return False


def test_smtp_connection(to_email: str | None = None) -> tuple[bool, str]:
    """Test SMTP connection, TLS handshake, authentication, and optional test email.

    Returns (success: bool, message: str) for live diagnostics.
    """
    if not settings.SMTP_HOST or not settings.SMTP_PORT:
        return (
            False,
            "SMTP_HOST o SMTP_PORT no están configurados en las variables de entorno.",
        )

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return (
            False,
            "SMTP_USER o SMTP_PASSWORD no están configurados en las variables de entorno.",
        )

    try:
        with _get_smtp_client(timeout=10) as server:
            _prepare_and_login(server)
            if to_email:
                msg = EmailMessage()
                msg["Subject"] = "Prueba de conectividad SMTP — SOS Animales"
                msg["From"] = settings.FROM_EMAIL
                msg["To"] = to_email
                msg.set_content(
                    "Este es un correo de prueba de diagnóstico enviado desde SOS Animales para verificar la configuración SMTP."
                )
                server.send_message(msg)
                return (
                    True,
                    f"Conexión exitosa y correo de prueba enviado a {to_email}.",
                )
            return (
                True,
                f"Conexión y autenticación exitosa con {settings.SMTP_HOST}:{settings.SMTP_PORT}.",
            )
    except TimeoutError:
        return (
            False,
            f"Timeout al conectar con el servidor SMTP ({settings.SMTP_HOST}:{settings.SMTP_PORT}) tras 10 segundos.",
        )
    except smtplib.SMTPAuthenticationError as e:
        return (
            False,
            f"Fallo de autenticación con el usuario '{settings.SMTP_USER}': {e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else e.smtp_error}",
        )
    except smtplib.SMTPConnectError as e:
        return (
            False,
            f"No se pudo establecer conexión con {settings.SMTP_HOST}:{settings.SMTP_PORT}: {e}",
        )
    except Exception as e:
        return False, f"Error inesperado al conectar con el servidor SMTP: {e}"
