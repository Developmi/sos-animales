# syntax=docker/dockerfile:1.7
# Stage 1: Build virtual environment with uv
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS builder

# Copy official uv binary from GHCR
COPY --from=ghcr.io/astral-sh/uv:0.5.24@sha256:2381d6aa60c326b71fd40023f921a0a3b8f91b14d5db6b90402e65a635053709 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock* ./

# Install production dependencies only into /app/.venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: Hardened runtime environment
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS runner

LABEL org.opencontainers.image.title="sos-animales" \
      org.opencontainers.image.description="Production-grade platform for animal rescue, adoption, and sterilization campaigns in Colombia" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/Developmi/sos-animales" \
      org.opencontainers.image.licenses="AGPL" \
      org.opencontainers.image.authors="Miguel Lozano <miguel@developmi.com>"

# Create dedicated non-root user (UID/GID 10001)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /sbin/nologin -M appuser

WORKDIR /app

# Copy isolated virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application source code and resources
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser migrations /app/migrations
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
COPY --chown=appuser:appuser data /app/data
COPY --chown=appuser:appuser seed /app/seed
COPY --chmod=755 --chown=appuser:appuser scripts/entrypoint.sh /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live').read()"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
