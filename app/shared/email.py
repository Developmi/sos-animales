import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_pin_email_sync(to_email: str, entity_name: str, pin: str) -> None:
    """Synchronous function to send management PIN email in background task.

    Sanitizes logging to comply with CWE-532 (no plaintext secrets in logs).
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            "SMTP not configured. Management PIN delivery simulated for: %s (redacted)",
            to_email,
        )
        return

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
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Management PIN successfully sent to: %s", to_email)
    except Exception as e:
        logger.error("Failed to send management PIN to %s: %s", to_email, e)
