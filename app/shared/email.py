"""Transactional email dispatching and diagnostics via modular provider adapters."""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

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


def _build_pin_email_body(entity_name: str, pin: str) -> str:
    """Generate plaintext body for management PIN delivery."""
    return f"""Hola,

Tu publicación de '{entity_name}' ha sido registrada en SOS Animales Colombia.

Tu PIN de seguridad de 4 dígitos es: {pin}

Conserva este código seguro. Lo necesitarás para gestionar directamente tu publicación:
• Marcar como Adoptado cuando el peludo encuentre hogar.
• Dar de baja o retirar la publicación si ya no está disponible o no autorizas el caso.

Para gestionar este caso, visita la ficha de '{entity_name}' e ingresa tu PIN.

Gracias por ayudar a proteger a los animales.
SOS Animales Colombia
https://sos-animales.org
"""


class EmailProvider(Protocol):
    """Protocol defining the transactional email provider interface."""

    def send_pin_email(self, to_email: str, entity_name: str, pin: str) -> bool:
        """Send management PIN to the entity creator. Returns True if sent successfully."""
        ...

    def test_connection(self, to_email: str | None = None) -> tuple[bool, str]:
        """Test provider connectivity, credentials, and optionally dispatch a test email."""
        ...


class SmtpEmailProvider:
    """Traditional SMTP transactional email provider using smtplib."""

    def send_pin_email(self, to_email: str, entity_name: str, pin: str) -> bool:
        """Send management PIN email via SMTP in background task.

        Sanitizes logging to comply with CWE-532 (no plaintext secrets in logs).
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
        msg.set_content(_build_pin_email_body(entity_name, pin))

        try:
            with _get_smtp_client(timeout=10) as server:
                _prepare_and_login(server)
                server.send_message(msg)
            logger.info("Management PIN successfully sent to: %s", to_email)
            return True
        except Exception as e:
            logger.error("Failed to send management PIN to %s: %s", to_email, e)
            return False

    def test_connection(self, to_email: str | None = None) -> tuple[bool, str]:
        """Test SMTP connection, TLS handshake, authentication, and optional test email."""
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


class ResendEmailProvider:
    """Modern transactional email provider using Resend REST API over HTTPS (port 443).

    Bypasses cloud provider egress port blocks (e.g. OCI blocking ports 25, 465, 587).
    """

    API_URL = "https://api.resend.com/emails"
    API_KEYS_URL = "https://api.resend.com/api-keys"

    @property
    def api_key(self) -> str:
        """Resolve Resend API key from RESEND_API_KEY or fallback to SMTP_PASSWORD if formatted as re_..."""
        if settings.RESEND_API_KEY:
            return settings.RESEND_API_KEY.strip()
        if settings.SMTP_PASSWORD and settings.SMTP_PASSWORD.startswith("re_"):
            return settings.SMTP_PASSWORD.strip()
        return ""

    def send_pin_email(self, to_email: str, entity_name: str, pin: str) -> bool:
        """Send management PIN email via Resend REST API in background task.

        Sanitizes logging to comply with CWE-532 (no plaintext secrets in logs).
        """
        api_key = self.api_key
        if not api_key:
            logger.warning(
                "Resend API key not configured. Management PIN delivery simulated for: %s (redacted)",
                to_email,
            )
            return False

        payload = {
            "from": settings.FROM_EMAIL,
            "to": [to_email],
            "subject": f"Tu PIN de administración para: {entity_name}",
            "text": _build_pin_email_body(entity_name, pin),
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code in (200, 201):
                logger.info(
                    "Management PIN successfully sent to: %s via Resend API", to_email
                )
                return True
            logger.error(
                "Failed to send management PIN to %s via Resend API (HTTP %d): %s",
                to_email,
                response.status_code,
                response.text,
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to send management PIN to %s via Resend API: %s", to_email, e
            )
            return False

    def test_connection(self, to_email: str | None = None) -> tuple[bool, str]:
        """Test Resend API credentials, connectivity over HTTPS (443), and optional test email."""
        api_key = self.api_key
        if not api_key:
            return (
                False,
                "RESEND_API_KEY no está configurado en las variables de entorno (ni se detectó prefijo re_ en SMTP_PASSWORD).",
            )

        if not settings.FROM_EMAIL:
            return (
                False,
                "FROM_EMAIL no está configurado en las variables de entorno.",
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                if to_email:
                    response = client.post(
                        self.API_URL,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "from": settings.FROM_EMAIL,
                            "to": [to_email],
                            "subject": "Prueba de conectividad Resend API — SOS Animales",
                            "text": "Este es un correo de prueba de diagnóstico enviado desde SOS Animales para verificar la integración con Resend API.",
                        },
                    )
                    if response.status_code in (200, 201):
                        return (
                            True,
                            f"Conexión exitosa con Resend API y correo de prueba enviado a {to_email}.",
                        )
                    return (
                        False,
                        f"Error al enviar correo de prueba vía Resend API (HTTP {response.status_code}): {response.text}",
                    )

                response = client.get(
                    self.API_KEYS_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if response.status_code == 200:
                    return (
                        True,
                        "Conexión y autenticación exitosa con la API de Resend (HTTPS:443).",
                    )
                if response.status_code == 401:
                    return (
                        False,
                        "Fallo de autenticación con Resend API: API Key inválida o revocada.",
                    )
                return (
                    False,
                    f"Respuesta inesperada de Resend API (HTTP {response.status_code}): {response.text}",
                )
        except httpx.TimeoutException:
            return (
                False,
                "Timeout al conectar con la API de Resend (https://api.resend.com) tras 10 segundos.",
            )
        except httpx.RequestError as e:
            return (
                False,
                f"Error de red al conectar con la API de Resend: {e}",
            )
        except Exception as e:
            return False, f"Error inesperado al conectar con Resend API: {e}"


def get_email_provider() -> EmailProvider:
    """Factory to retrieve configured EmailProvider implementation."""
    provider_name = (settings.EMAIL_PROVIDER or "smtp").lower().strip()
    if provider_name == "resend":
        return ResendEmailProvider()
    return SmtpEmailProvider()


def send_pin_email_sync(to_email: str, entity_name: str, pin: str) -> bool:
    """Synchronous function to send management PIN email in background task.

    Delegates to configured EmailProvider (SMTP or Resend).
    Sanitizes logging to comply with CWE-532 (no plaintext secrets in logs).
    Returns True if sent successfully, False otherwise.
    """
    provider = get_email_provider()
    return provider.send_pin_email(to_email, entity_name, pin)


def test_smtp_connection(to_email: str | None = None) -> tuple[bool, str]:
    """Test email connectivity and credentials for current provider.

    Maintains backward compatibility with CLI and maintenance endpoints.
    Returns (success: bool, message: str) for live diagnostics.
    """
    provider = get_email_provider()
    return provider.test_connection(to_email=to_email)


# Alias for modern provider-agnostic naming
test_email_connection = test_smtp_connection
