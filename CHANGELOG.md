# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
