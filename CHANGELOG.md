# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-11-02

### Added
- **Full Admin CRUD Management Suite**:
  - Implemented centralized administrative management interfaces for **Fundaciones & Refugios** (`/admin/sources`), **Jornadas de Esterilización** (`/admin/sterilizations`), and **Peluditos en Adopción** (`/admin/animals`).
  - Added full create, edit, deactivate/delete, and status update capabilities protected by `Role.ADMIN` session authentication.
  - Added responsive sub-navigation tabs across all admin sections with Warm Humanist styling and accessible SVG icons.
- **Accessible Lightbox Modal & Responsive Photo Gallery**:
  - Added click-to-zoom interactive modal lightbox for full-resolution pet photo viewing with accessible keyboard controls (Escape to close) and focus management.
  - Updated pet photo containers with adaptable aspect ratios and subtle backdrop to prevent clipping or cropping of vertical portrait photos.
  - Unified photo gallery in animal detail view to render all uploaded images (N=3+), fixing previous thumbnail hiding bug and allowing switching back to primary photo.
- **Resilient SMTP Transport & Live Diagnostics CLI**:
  - Added automatic detection for SSL direct connection (`smtplib.SMTP_SSL`) on port 465 alongside STARTTLS on port 587 with strict 10s socket timeout.
  - Added operational CLI diagnostic command `python -m app.cli test-smtp [--to email]` and Makefile target `make test-smtp` for live end-to-end verification.

### Fixed
- **Leaflet Marker Asset 404 Resolution**:
  - Resolved relative CSS marker image lookup (`marker-icon.png`, `marker-shadow.png`) by synchronizing assets to `app/static/css/vendor/images/` and configuring explicit `L.Icon.Default.imagePath`.
- **Adoption Policies Terms Acceptance Validation**:
  - Fixed client-side validation in `profile_form.html` to prevent bypassing adoption policies terms agreement on form submission.
  - Enforced strict `accept_terms: bool = Form(False)` default in FastAPI endpoint to require explicit affirmative consent under Ley 1581 de 2012.

## [1.0.3] - 2026-11-01

### Added
- **Zero-CDN Offline Vendor Assets**:
  - Downloaded, validated, and vendored official pinned distributions of HTMX (`v2.0.4`) and Leaflet (`v1.9.4`) into `app/static/js/vendor/` and `app/static/css/vendor/` with complete marker images in `app/static/images/vendor/leaflet/`.
  - Added deterministic automated tool `tools/vendor.sh` and `make vendor` target with pre-flight Gate 0 checks, linter sweeps, and Trivy filesystem vulnerability gates before downloading and unpacking.
- **Official Favicon Integration**:
  - Organized project favicon into `app/static/favicon.ico` with dedicated FastAPI endpoint (`GET /favicon.ico`) and layout head linkage across all HTML templates.

### Security
- **Perimeter CSP Zero-CDN Hardening**:
  - Stripped external CDNs (`unpkg.com`, `cdn.jsdelivr.net`) from Content Security Policy headers in `proxy/Caddyfile`, eliminating third-party supply-chain and tracking vectors while restricting tile and asset connections to self and OpenStreetMap.

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
