# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.2] - 2026-10-30

### Added
- **Multi-Arch OCI Container Build**:
  - Enabled multi-architecture OCI build and publish for `linux/amd64` and `linux/arm64` using `docker/setup-qemu-action` in `.github/workflows/container.yml` with Cosign keyless signing and SLSA build provenance attestations.
- **Perimeter Caddy WAF Reverse Proxy (`proxy/`)**:
  - Added hardened Caddy WAF distribution integration (`Dockerfile`, `Caddyfile`, `README.md`) based on `ghcr.io/developmi/caddy-waf:v3.6.2` featuring Coraza WAF in `DetectionOnly` mode, 10MB multipart photo upload body limits, perimetral rate limiting, and customized Content Security Policy supporting Leaflet OpenStreetMap tiles and HTMX.
- **Dual Emergency Maintenance Mode**:
  - Implemented full-stack maintenance mode (`app/shared/maintenance.py`, `app/cli.py`, `MaintenanceMiddleware`) with interactive HTMX toggle in Admin Panel (`/admin/`), operational CLI commands (`python -m app.cli maintenance on|off|status` / `make maintenance-on|off`), Valkey state persistence with local sentinel file fallback, and HTTP 503 Warm Humanist maintenance page (`app/shared/templates/maintenance.html`) while preserving `/health/*`, `/auth/*`, `/admin/*`, and `/static/*`.

### Changed
- **Automated Test Backing Services**:
  - Enhanced `Makefile` (`make test`, `make test-services`) to automatically initialize, migrate, and seed backing PostgreSQL and Valkey services before running integration tests.

## [1.0.1] - 2026-10-25

### Added
- **Statutory Data Governance & Privacy Compliance**:
  - Integrated strict compliance with Colombian Law 1581 of 2012 / SIC Concept 18-174082 requiring explicit statutory consent on `POST /sources/register` and `POST /community/update`.
- **NIST SP 800-63B Anti-Brute Force Protection**:
  - Added global per-entity 15-attempt circuit breaker on animal profile PIN validation (`POST /animals/{id}/adopt`).
- **Dual-Key Community Voting Anti-Rotation**:
  - Enforced anti-rotation voting rate limiting via subnet key combined with signed `sos_voter_token` HTTP cookie.

### Security
- **Anonymized IP Privacy Hashing**:
  - Implemented daily-salted `HMAC-SHA256(SECRET_KEY + YYYY-MM-DD, subnet)` with `/64` IPv6 normalization across all Valkey rate limit keys.
- **Production Baseline Sanitization**:
  - Segregated synthetic demo fixtures (`seed/demo.py`) from the production catalog, ensuring zero synthetic demo data on container startup.
- **Loopback Ingress Hardening**:
  - Restricted default Docker container port mapping to `127.0.0.1:${WEB_PORT:-8000}:8000` for Caddy and Tailscale VPS deployments.

## [1.0.0] - 2026-10-23

### Added
- **Comprehensive Contract & TDD Shield (92% Global Coverage)**:
  - 293 automated tests across `animals`, `sterilization`, `community`, `sources`, `verification`, `auth`, and `shared/security` with 100% router and security coverage.
- **Dynamic Foundation Selector on Animal Publishing (`GET /animals/new`)**:
  - Replaced hardcoded `source_id=1` with dynamic active foundation selector and `?source_id=` pre-selection from foundation profiles.
- **Supply Chain & CI/CD Governance**:
  - Added `.github/dependabot.yml` monitoring `uv`, `github-actions`, and `docker` ecosystems weekly.
- **Core Domain Modules**:
  - `sterilization`: Management and geo-search for sterilization campaigns and permanent fixed points.
  - `sources`: Shelter and foundation registry with structured two-tier validation.
  - `animals`: Pet adoption profiles with photo management via Cloudflare R2 (`boto3`).
  - `community`: Citizen status reporting with IP rate-limiting in Valkey and voting thresholds.
  - `verification`: Veterinarian checklist and on-site inspection workflows.
  - `auth`: Admin session governance with bcrypt, JWT (`PyJWT`), and secure httpOnly cookies.
- **SRE & Reliability**:
  - Decoupled health probes: `GET /health/live` and `GET /health/ready` verifying PostgreSQL and Valkey.
  - Resilient SQLAlchemy async engine with `pool_pre_ping=True`, timeouts, and pool limits.
  - Reverse proxy header forwarding (`ProxyHeadersMiddleware`) for accurate client IP rate limiting.
- **Security & Hardening**:
  - Multi-stage rootless `Dockerfile` running as unprivileged `appuser:10001` with `uv`.
  - Hardened `docker-compose.yml` with `cap_drop: [ALL]`, `no-new-privileges:true`, and loopback `127.0.0.1` port bindings.
  - Sanitized logging: zero plaintext PIN exposure in stdout and HTML responses.
  - OpenVEX governance template (`vex/sos-animales-vex.json`).
- **CI/CD Automation**:
  - Hardened GitHub Actions workflows (`lint.yml`, `test.yml`, `container.yml`) with immutable SHA-40 action pinning and least-privilege `permissions: {}`.
  - Automated OCI container building and Trivy vulnerability scanning (`container.yml`).
