"""Configuración vía pydantic-settings desde variables de entorno.

Variables expuestas:
- DATABASE_URL (str): conexión async a PostgreSQL
- SECRET_KEY (str): clave para firma interna
- PLAUSIBLE_DOMAIN / PLAUSIBLE_URL (str | None): analytics opt-in
- COMMUNITY_VOTE_THRESHOLD (int): mínimo de votos para que comunidad sobreescriba estado oficial (default: 5)
- SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD: correo transaccional para envío de PINs
- R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME / R2_PUBLIC_URL: fotos en Cloudflare R2
"""
