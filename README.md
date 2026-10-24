<div align="center">

<!-- TODO: add logo to docs/assets/logo.png -->

# SOS Animales | Developmi

_National open-data platform connecting citizens, animal shelters, and veterinarians across Colombia to locate sterilization campaigns, verify foundations through two-tier veterinary audits, and accelerate verified pet adoptions without intermediary friction._

![Python](https://img.shields.io/badge/Python_|_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI_|_0.138+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_|_17.4-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Valkey](https://img.shields.io/badge/Valkey_|_8.0-FF4438?style=for-the-badge&logo=redis&logoColor=white)
![uv](https://img.shields.io/badge/uv_|_Package_Manager-DE5FE9?style=for-the-badge&logo=uv&logoColor=white)
![Docker](https://img.shields.io/badge/Docker_|_READY-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Status](https://img.shields.io/badge/Status-Production_Stable-brightgreen?style=for-the-badge)
![License](https://img.shields.io/badge/License-AGPL--3.0_©_Miguel_Lozano_|_Developmi-blue?style=for-the-badge)
![Maintainer](https://img.shields.io/badge/Maintainer-Miguel_Lozano-black?style=for-the-badge)![Role](https://img.shields.io/badge/Cloud_&_Infrastructure_Engineer-333?style=for-the-badge)
![CI](https://img.shields.io/badge/CI-Passing-brightgreen?style=for-the-badge&logo=githubactions&logoColor=white)

</div>

---

## Table of contents

- [Overview](#-overview)
- [Quick start](#-quick-start)
- [Architecture](#-architecture)
- [Docker deployment](#-docker-deployment)
- [Configuration](#-configuration)
- [Tests](#-tests)
- [Security](#-security)
- [Changelog](#-changelog)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact & support](#-contact--support)

---

## 🎯 Overview

Fragmented information across social media prevents pet owners and animal rescuers in Colombia from finding active low-cost sterilization campaigns, permanent veterinary clinics, and trustworthy shelters. **SOS Animales** centralizes national animal welfare data across all **33 departments and 1,123 municipalities of Colombia**, enabling citizens to locate verified sterilization events, publish adoptable animals assigned to audited foundations, and validate field reports in real time without requiring public user registration or intermediaries.

Built on an asynchronous **FastAPI + SQLAlchemy 2.0 (`asyncpg`) + PostgreSQL 17** backend paired with a zero-build **HTMX + Pure CSS3 + Leaflet JS** frontend, the platform enforces strict domain isolation (`models.py`, `schemas.py`, `tools.py`, `router.py`), Valkey 8 rate limiting, and Cloudflare R2 object storage for animal photography.

### Access & Verification Governance (Phase 1 MVP)

In Phase 1 (v1.0.0), the platform operates without public user account registration to eliminate adoption and reporting friction while maintaining strict anti-abuse controls:

- **Official Campaigns & Veterinary Audits:** Creating sterilization campaigns (`POST /sterilization/new`), permanent fixed points (`POST /sterilization/fixed-points`), and veterinary inspection visits (`POST /verification/visit`) requires centralized administrator authentication (`/auth/login`) backed by `bcrypt` and `httpOnly` JWT cookies.
- **Adoptions & Foundation Self-Registration:** Foundations and shelters can self-register (`POST /sources/register`, entering a `pending` state until audited) and rescuers can publish animals for adoption (`POST /animals/`) linked to an active foundation (`source_id`). Upon publication or community status reporting, the submitter receives a cryptographic 4-digit PIN via transactional email to manage or mark the animal as adopted (`POST /animals/{id}/adopt`) without permanent passwords.
- **Citizen Interaction & Consensus:** Citizens browse interactive maps, submit PIN-verified status updates (`POST /community/update`), and vote on community updates (`POST /community/vote/{id}`) protected by IP rate limiting in Valkey.

### Key Capabilities

- **Security:**
  - Single-admin authentication using `bcrypt` password hashing and `PyJWT` (`HS256`) stored in `httpOnly`, `SameSite=Lax` cookies.
  - Multi-layer Valkey rate limiting protecting `/auth/login` (5 req/min/IP), community update creation (10 req/hour/target/IP), PIN brute-force validation (5 failed attempts/hour/IP with automatic reset on success), and duplicate voting (24h IP lock).
  - Hardened rootless OCI container (`appuser:10001`), `cap_drop: [ALL]`, `no-new-privileges:true`, and SHA-40 pinned GitHub Actions workflows verified by `zizmor`, `actionlint`, `hadolint`, and `Trivy`.
- **Performance:**
  - 100% non-blocking database I/O powered by `SQLAlchemy[asyncio]` and `asyncpg` against PostgreSQL 17 with `pool_pre_ping=True`.
  - Zero JavaScript build step: server-rendered Jinja2 templates enhanced with HTMX partial swaps and Leaflet JS maps for sub-100ms UI interactions on low-bandwidth mobile networks.
- **Architecture:**
  - Six decoupled domain modules (`auth`, `sterilization`, `sources`, `verification`, `animals`, `community`) where pure business logic in `tools.py` is strictly separated from FastAPI HTTP routers.
  - Decoupled Kubernetes/Docker health probes (`GET /health/live` and `GET /health/ready`) and operational SRE runbooks under `docs/runbooks/`.
- **FinOps / Cost:**
  - Ultra-lightweight runtime footprint capable of running on a single bare-metal or VPS node alongside Cloudflare R2 free-tier object storage and Google SMTP free tier, with local SVG placeholder fallback when R2 credentials are omitted.

---

## ⚡ Quick start

### Prerequisites

| Tool | Minimum Version | Purpose |
|---|---|---|
| **Python** | `3.12+` | Application runtime |
| **uv** | `0.5+` | Exclusive Python package and virtual environment manager |
| **Docker & Docker Compose** | `26.0+` / `v2.24+` | PostgreSQL 17, Valkey 8, and containerized stack execution |
| **GNU Make** | `4.0+` | Developer workflow and DevSecOps gate orchestration |

> **Note:** Never use `npm install`, `yarn`, or `pip install` in this project. All Python dependencies and virtual environments are managed exclusively via `uv` (`uv.lock`).

### Option A: Local Development with `uv` (Recommended)

```bash
# 1. Clone the repository and synchronize the locked environment
git clone https://github.com/Miguel-DevOps/sos-animales.git
cd sos-animales
uv sync

# 2. Initialize environment configuration from the root Single Source of Truth
cp .env.example .env
# Optional: generate a bcrypt hash for ADMIN_PASSWORD_HASH to access /admin/
uv run python scripts/hash_admin.py

# 3. Start PostgreSQL 17 (host port 5433) and Valkey 8 (host port 6379)
docker compose up -d db valkey

# 4. Apply Alembic migrations and seed Colombia's 33 departments & 1,123 municipalities
make migrate
uv run python -m seed

# 5. Start the FastAPI development server with hot-reload on http://127.0.0.1:8000
make dev
```

### Option B: 100% Containerized Execution

```bash
# Build and start the full stack (web + db + valkey) in the background
make up

# Apply database migrations and idempotent initial seed inside the web container
docker compose exec web alembic upgrade head
docker compose exec web python -m seed

# Stream real-time aggregated logs
make logs
```

### Data Seeding & Geographic Refresh

The idempotent seed module (`seed/`) preloads static geographic datasets from `data/colombia/`:

- **33 departments** and **1,123 municipalities** across Colombia.
- **Demo dataset**: verified sterilization campaigns, foundations/shelters, adoptable animals, and veterinary verification visits.

To refresh the geographic JSON dataset from the open Colombia API (`api-colombia.com`):

```bash
uv run python scripts/fetch_colombia_data.py
uv run python -m seed
```

### Administration Panel

The administrator dashboard is located at `/admin/`:

1. Navigate to `/auth/login` and authenticate with the administrator password matching `ADMIN_PASSWORD_HASH`.
2. The session issues a signed JWT stored in an `httpOnly` cookie (`access_token`).
3. From `/admin/`, inspect real-time platform statistics (campaigns, animals, foundations, fixed points) and execute restricted creation/verification workflows.

---

## 🏗️ Architecture

### Repository Structure (2-Level Annotated Tree)

```text
sos-animales/
├── .github/
│   ├── dependabot.yml          # Weekly automated dependency updates (uv, github-actions, docker)
│   └── workflows/              # Hardened SHA-40 pinned CI/CD pipelines (lint.yml, test.yml, container.yml)
├── app/
│   ├── config.py               # Pydantic Settings validation reading root .env SSOT
│   ├── database.py             # Async SQLAlchemy 2.0 engine & session factory (asyncpg)
│   ├── main.py                 # FastAPI entrypoint, middlewares, health probes & exception handlers
│   ├── domains/                # 6 isolated business domains (auth, sterilization, sources, verification, animals, community)
│   ├── shared/                 # Cross-cutting services (Valkey security/rate-limiting, Nominatim geo, SMTP email, R2 storage)
│   └── static/                 # Zero-build static assets (Pure CSS design system & client JS helpers)
├── data/
│   └── colombia/               # Offline JSON datasets for 33 departments and 1,123 municipalities
├── docs/
│   └── runbooks/               # Operational SRE incident runbooks (DB pool, reverse proxy IP, Valkey failover)
├── migrations/
│   └── versions/               # Alembic schema migrations for PostgreSQL
├── scripts/
│   ├── entrypoint.sh           # Container startup script (Alembic migrations + Uvicorn launch)
│   ├── fetch_colombia_data.py  # Geographic dataset synchronization utility
│   └── hash_admin.py           # Interactive bcrypt password hash generator for ADMIN_PASSWORD_HASH
├── seed/
│   └── seed_data.py            # Idempotent database seeding for Colombia geography and demo entities
├── tests/
│   ├── domains/                # Domain unit, integration, and router contract test suites
│   └── shared/                 # Security, Valkey lifecycle, SRE resilience, geo, and email test suites
├── tools/
│   ├── install.sh              # Deterministic installer for pinned actionlint, hadolint, and trivy binaries
│   └── versions.mk             # Single Source of Truth for external binary versions
├── vex/
│   └── sos-animales-vex.json   # OpenVEX supply-chain vulnerability exploitability statement
├── .dockerignore               # Context exclusion rules for minimal OCI build context
├── .env.example                # Single Source of Truth (SSOT) template for all environment variables
├── .gitignore                  # Git exclusion rules including cryptographic and SBOM patterns
├── Dockerfile                  # Multi-stage rootless Docker build (Python 3.12-slim + uv + appuser:10001)
├── Makefile                    # Enterprise DevSecOps command runner
├── docker-compose.yml          # Hardened local & production service orchestration (web, db, valkey)
├── pyproject.toml              # Project metadata, dependencies, Ruff, Mypy strict, and Pytest config
└── uv.lock                     # Deterministic cross-platform dependency lockfile
```

### System Data-Flow Diagram

```mermaid
flowchart TD
    subgraph Client["Client / Browser"]
        UI["HTMX + Pure CSS Design System + Leaflet JS"]
    end

    subgraph AppServer["FastAPI Application (app/main.py)"]
        Main["FastAPI Router & ProxyHeadersMiddleware"]

        subgraph Domains["Modular Business Domains (app/domains/)"]
            Auth["auth (JWT / bcrypt / Admin Panel)"]
            Sterilization["sterilization (Campaigns & Fixed Points)"]
            Animals["animals (Adoption Profiles & Foundation Link)"]
            Sources["sources (Foundations & Shelters)"]
            Community["community (PIN Reports & Consensus Voting)"]
            Verification["verification (Veterinary Visits & Checklists)"]
        end

        Shared["shared (Valkey Security, Nominatim Geo, SMTP Email, R2 Storage)"]
    end

    subgraph DataStorage["Persistence, Cache & Object Storage"]
        PG[("PostgreSQL 17 (SQLAlchemy asyncpg)")]
        VK[("Valkey 8 (Rate Limiting & Cache)")]
        R2[("Cloudflare R2 (Animal Photos)")]
    end

    UI <-->|HTTP / HTMX Partial Swap| Main
    Main --> Domains
    Domains --> Shared
    Domains --> PG
    Shared --> VK
    Animals --> R2
```

### Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI + SQLAlchemy 2.0 Async (`asyncpg`) |
| **Database** | PostgreSQL 17 (exclusively PostgreSQL with `asyncpg`) |
| **Frontend** | HTMX + Pure CSS3 (`sos-animales.css`) + Jinja2 (zero JS build step) |
| **Cache & Rate Limiting** | Valkey 8 (Redis-compatible) |
| **Geocoding & Maps** | Leaflet JS + OpenStreetMap / Nominatim |
| **Object Storage** | Cloudflare R2 (`boto3` S3-compatible API) |
| **Package Manager** | `uv` (exclusive, zero `pip` / `npm`) |
| **Authentication** | JWT (`PyJWT`) + `bcrypt` + `httpOnly` secure cookies |
| **Automation & QA** | `Makefile` + Docker Compose + GitHub Actions |

### Domain Isolation Matrix

Each domain inside `app/domains/` encapsulates its own `models.py`, `schemas.py`, `tools.py`, and `router.py`:

| Domain | Responsibility |
|---|---|
| `auth` | Administrator JWT authentication (`httpOnly` cookie), `/admin/` dashboard, and login rate limiting |
| `sterilization` | Sterilization campaigns, permanent veterinary fixed points, and geographic/price filtering |
| `sources` | Foundation and shelter directory with `pending` / `verified` / `rejected` lifecycle states |
| `verification` | Two-tier veterinary verification requests, inspection checklists, and audit visit records |
| `animals` | Adoptable animal profiles, Cloudflare R2 photo upload, dynamic foundation assignment, and PIN-authorized adoption state transitions |
| `community` | PIN-authenticated community status updates and IP rate-limited consensus voting |

### Data Governance Rules

- **Freshness Policy:** Records without confirmation for `FRESHNESS_DAYS` (default: 5 days) are flagged as unconfirmed with a visual warning; records exceeding `FRESHNESS_HIDE_DAYS` (default: 15 days) are hidden from default public listings.
- **Two-Tier Veterinary Verification:** In-person inspection (within a ≤ 2-hour radius from Bogotá) or remote audit via verified regional veterinary allies.
- **Community vs. Official Consensus:** Requires a configurable minimum number of community votes (`COMMUNITY_VOTE_THRESHOLD`, default: 5) before a community report overrides an official status.
- **Strict Scope Boundaries:** Zero money/donation handling, zero public user accounts, zero internal chat, and zero commercial WhatsApp Cloud APIs. For phase details, see [ROADMAP.md](./ROADMAP.md).

---

## 🐳 Docker deployment

The repository ships a hardened multi-stage [`Dockerfile`](./Dockerfile) and [`docker-compose.yml`](./docker-compose.yml) orchestrating three services (`web`, `db`, `valkey`).

### Build and Run Commands

```bash
# Validate docker-compose configuration syntax
make compose-config

# Build the local hardened OCI image (sos-animales:local)
make docker-build

# Start the complete stack (PostgreSQL 17, Valkey 8, and FastAPI web)
make up

# Inspect container health status and stream logs
make ps
make logs-web
```

### Container Hardening & SRE Probes

> **Security Callout — Rootless & Least-Privilege Execution:**
> - The runtime image executes strictly as unprivileged user `appuser` (`UID 10001` / `GID 10001`) with `/sbin/nologin` shell and bytecode pre-compiled via `uv sync --frozen --no-dev --compile-bytecode`.
> - [`docker-compose.yml`](./docker-compose.yml) drops all Linux kernel capabilities (`cap_drop: [ALL]`), enforces `security_opt: [no-new-privileges:true]`, mounts `tmpfs` for `/tmp`, and binds host ports strictly to loopback (`127.0.0.1:8000`, `127.0.0.1:5433`, `127.0.0.1:6379`).
> - Container startup is governed by [`scripts/entrypoint.sh`](./scripts/entrypoint.sh), which runs `alembic upgrade head` before replacing the shell process (`exec`) with `uvicorn`.
> - **Health Checks:** Liveness is exposed at `GET /health/live` (`200 OK`) and readiness (verifying live PostgreSQL `SELECT 1` and Valkey `PING` connectivity) at `GET /health/ready`. Operational incident procedures are documented in [`docs/runbooks/`](./docs/runbooks/).

---

## 🔧 Configuration

The root [`.env.example`](./.env.example) file is the **Single Source of Truth (SSOT)** for all environment variables across local development, testing, and Docker Compose deployments. Do not create separate `.env` files inside subdirectories.

| Category | Variable | Default / Example | Required | Description |
|---|---|---|---|---|
| **Database** | `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5433/sos_animales` | Yes | Async SQLAlchemy PostgreSQL connection URI |
| **Database** | `POSTGRES_USER` | `user` | Yes (Compose) | PostgreSQL superuser for container initialization |
| **Database** | `POSTGRES_PASSWORD` | `pass` | Yes (Compose) | PostgreSQL password for container initialization |
| **Database** | `POSTGRES_DB` | `sos_animales` | Yes (Compose) | PostgreSQL database name |
| **Database** | `POSTGRES_PORT` | `5433` | No | Host loopback port mapped to PostgreSQL container `5432` |
| **Database** | `DATABASE_ECHO` | `false` | No | Log all generated SQL statements when `true` |
| **Cache & Rate Limit** | `VALKEY_URL` | `redis://localhost:6379/0` | Yes | Valkey 8 connection URI for rate limiting and caching |
| **Security & Auth** | `SECRET_KEY` | `change-me` | Yes | Internal cryptographic signing secret |
| **Security & Auth** | `ADMIN_PASSWORD_HASH` | `generate_with_uv_run_python_scripts_hash_admin_py` | Yes | Bcrypt hash of the administrator password |
| **Security & Auth** | `JWT_SECRET` | `replace-with-a-random-secret-key-at-least-32-chars` | Yes | Secret key used to sign and verify `HS256` admin JWT cookies |
| **Security & Auth** | `JWT_EXPIRE_MINUTES` | `480` | No | Administrator JWT session lifetime in minutes |
| **Governance** | `COMMUNITY_VOTE_THRESHOLD` | `5` | Yes | Minimum community votes required to override official status |
| **Governance** | `FRESHNESS_DAYS` | `5` | No | Days before an unconfirmed record displays a staleness warning |
| **Governance** | `FRESHNESS_HIDE_DAYS` | `15` | No | Days before an unconfirmed record is hidden (must be `> FRESHNESS_DAYS`) |
| **SMTP Email** | `SMTP_HOST` | `smtp.gmail.com` | Yes | SMTP server hostname for transactional 4-digit PIN emails |
| **SMTP Email** | `SMTP_PORT` | `587` | Yes | SMTP server TLS port |
| **SMTP Email** | `SMTP_USER` | _(empty in template)_ | Yes | SMTP authentication username |
| **SMTP Email** | `SMTP_PASSWORD` | _(empty in template)_ | Yes | SMTP authentication password or app password |
| **SMTP Email** | `FROM_EMAIL` | _(empty in template)_ | Yes | Sender email address for PIN notifications |
| **Cloudflare R2** | `R2_ENDPOINT` | _(optional)_ | No | Cloudflare R2 S3-compatible endpoint URL |
| **Cloudflare R2** | `R2_ACCESS_KEY_ID` | _(optional)_ | No | R2 API access key ID |
| **Cloudflare R2** | `R2_SECRET_ACCESS_KEY` | _(optional)_ | No | R2 API secret access key |
| **Cloudflare R2** | `R2_BUCKET_NAME` | `sos-animales-fotos` | No | Target R2 bucket name for animal photos |
| **Cloudflare R2** | `R2_PUBLIC_URL` | `https://pub-xxxxxx.r2.dev` | No | Public CDN/bucket base URL for rendering uploaded photos |
| **Analytics** | `PLAUSIBLE_DOMAIN` | _(optional)_ | No | Plausible Analytics domain (loaded only after explicit cookie consent) |
| **Analytics** | `PLAUSIBLE_URL` | _(optional)_ | No | Custom Plausible script URL |

---

## 🧪 Tests

The repository enforces a comprehensive **293-test TDD and contract suite** achieving **92% global statement coverage** (and 100% coverage across domain routers and security primitives).

```bash
# Run the complete pytest suite
uv run pytest
# or via Makefile:
make test

# Run isolated fast unit tests (tools, geo, email, security)
make test-unit

# Run database & Valkey integration and router contract tests
make test-integration

# Enforce the strict statement coverage gate (>= 80% required, current: 92%)
make test-coverage-gate

# Run the complete multi-layer QA gate (Ruff, Mypy strict, yamllint, actionlint, hadolint, zizmor, pytest coverage)
make check

# Run the full pre-release gate (lint + coverage gate + compose validation + Docker build + Trivy scan)
make release-ready
```

Continuous Integration runs automatically on every push and pull request targeting `main` via GitHub Actions ([`.github/workflows/lint.yml`](./.github/workflows/lint.yml), [`.github/workflows/test.yml`](./.github/workflows/test.yml), and [`.github/workflows/container.yml`](./.github/workflows/container.yml)).

---

## 🔒 Security

This project follows a coordinated disclosure policy.
If you discover a vulnerability, **do not open a public issue**.
See [SECURITY.md](./SECURITY.md) for reporting instructions and response timelines.

---

## 📋 Changelog

See [CHANGELOG.md](./CHANGELOG.md) for the full version history.
The project follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

---

## 🤝 Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](./CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) before opening a pull request.
This project follows [Conventional Commits](https://www.conventionalcommits.org/) and the Developmi engineering standard.

---

## 📄 License

Copyright © 2024–2026 Miguel Lozano | Developmi. All rights reserved.
Licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](./LICENSE). Any modified version operated as a network service must make its complete source code publicly available under the same license.

---

## 🤝 Contact & support

**Maintained by:** Miguel Lozano | Developmi

- **Role:** Cloud & Infrastructure Engineer | FinOps & Bare Metal Specialist
- **Philosophy:** _Security is not a feature; it is the baseline._
- **Website:** [developmi.com](https://developmi.com)
- **GitHub:** [Miguel Lozano](https://github.com/Miguel-DevOps)
- **LinkedIn:** [Miguel Lozano](https://www.linkedin.com/in/miguel-dev-ops)

---

© 2026 Miguel Lozano | Developmi. All rights reserved.
