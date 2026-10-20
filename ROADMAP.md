# Roadmap — SOS Animales

> ⚠️ **For anyone reading this**: This roadmap is designed so that any engineer can understand WHAT needs to be built, IN WHAT ORDER, and WHEN each module is considered "done". If something is unclear, it is due to a lack of documentation clarity — not because "it is obvious".
>
> 📅 **Last updated: October 2026** — Phase 1 MVP is fully completed and operational. Sections marked as COMPLETED reflect the actual production-ready code state.

---

## 📌 Project Philosophy

SOS Animales is an **open data platform** that centralizes three core services on a single interactive map across Colombia:

1. **Sterilization campaigns** (free or low-cost mobile and fixed point clinics).
2. **Adoption animal profiles** with verified photos, species, and medical status.
3. **Verified shelters and foundations** (vetted through a structured two-tier audit process).

**What SOS Animales is NOT:**
- ❌ Does not process financial transactions (no donations, no payments, no monetary intermediation).
- ✅ Includes single-user administrative authentication (admin credentials to manage and safeguard data ingestion).
- ❌ Does not feature internal chat or messaging systems.
- ❌ Does not integrate commercial WhatsApp Cloud APIs (relies on direct links and email PIN notifications).

**The core mission is 100% informational:** display accurate, fresh, and trustworthy animal welfare data.

---

## 🧱 Technical Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Backend | FastAPI + Python 3.12+ | High-performance asynchronous execution, automatic validation via Pydantic v2 |
| Database | PostgreSQL 17 | Relational, ACID-compliant, robust indexing and geographic coordinates support |
| DB Driver | `asyncpg` | High-throughput asynchronous PostgreSQL connectivity |
| ORM | SQLAlchemy 2.0 (asyncio) | Asynchronous object-relational mapping, database migrations managed via Alembic |
| Frontend | HTMX + Pure CSS3 (`sos-animales.css`) | No JavaScript build step required, responsive mobile-first UI, sub-second load times |
| Templates | Jinja2 | Clean server-side HTML rendering natively integrated with FastAPI |
| Maps | Leaflet + OpenStreetMap | Free, open-source mapping stack requiring no proprietary API keys |
| Geocoding | Nominatim (OSM) | Converts municipality/neighborhood strings to geographic coordinates |
| Media Storage | Cloudflare R2 | OCI S3-compatible cloud object storage for adoption photos |
| Email / Notifications | Asynchronous SMTP | Outbound transactional PIN notifications |
| Cache & Rate Limiting | Valkey 8 | High-performance Redis-compatible in-memory store for rate limiting and cache |
| Quality & Tooling | `uv`, Ruff, Mypy (`--strict`), Pytest | Fast package management, linting, strict static typing, and 100% test coverage |

---

## 🗺️ Phase 1 — MVP (Completed)

### Definition of "MVP"

MVP = **Minimum Viable Product**. The most focused functional version that delivers genuine public utility. It validates core assumptions without unneeded architectural overhead.

### MVP "Done" Criteria

The Phase 1 MVP is considered complete when:
1. A citizen can access the web application, filter sterilization campaigns by municipality/species, and view geographic results on a Leaflet map.
2. A foundation/shelter can register public contact details (initial state set to `pending`).
3. Citizens can browse searchable profiles of adoptable pets with verified photos.
4. The community can report field updates (confirm, report full capacity, cancel, or flag errors) governed by 4-digit security PINs and rate limiting.
5. An administrator or volunteer veterinarian can record structured verification visits.
6. The entire codebase passes strict automated quality gates (`make check`: Ruff, Mypy strict, 134 automated tests).

---

## 📋 Phase 1 — Complete Task Breakdown

Each task specifies: **components involved**, **definition of done**, and **prerequisites**.

---

### 🔵 Pillar 0: Core Infrastructure — COMPLETED

#### 0.1 — Environment and Package Management (`pyproject.toml`) — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Modern project configuration with `pyproject.toml`, virtual environment via `uv`, and configuration templates. |
| **Files** | `pyproject.toml`, `.env.example`, `.python-version` |
| **Prerequisites** | None |
| **Done Criteria** | `uv run python -c "import fastapi; import sqlalchemy; import asyncpg; print('ok')"` succeeds with zero errors |

---

#### 0.2 — Asynchronous PostgreSQL Configuration — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Asynchronous engine setup, session factories, and dependency injection for PostgreSQL via `asyncpg`. |
| **Files** | `app/database.py`, `app/config.py`, `.env.example` |
| **Prerequisites** | 0.1 |
| **Done Criteria** | Application connects asynchronously using `DATABASE_URL` and yields clean sessions via `get_db()` |

---

#### 0.3 — Database Migrations via Alembic — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Asynchronous Alembic migration pipeline configured against SQLAlchemy declarative models. |
| **Files** | `alembic.ini`, `migrations/env.py`, `migrations/versions/` |
| **Prerequisites** | 0.2 |
| **Done Criteria** | `uv run alembic upgrade head` successfully executes all schema revisions |

---

#### 0.4 — Static Files and Base UI Templates — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Jinja2 templating architecture, static assets mount, HTMX integration, and responsive layout. |
| **Files** | `app/main.py`, `app/shared/templates/base.html`, `app/static/css/sos-animales.css` |
| **Prerequisites** | 0.1 |
| **Done Criteria** | Navigating to `/` renders semantic HTML layout with Leaflet and HTMX bundles |

---

### 🩵 Pillar 1: Sources (Shelters & Foundations) — COMPLETED

#### 1.1 — Source Entity Model — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Relational `sources` table containing identity, verification level, location, and contact metadata. |
| **Files** | `app/domains/sources/models.py`, Alembic revisions |
| **Prerequisites** | 0.3 |
| **Done Criteria** | Table `sources` created with indexes and enum constraints |

---

#### 1.2 — Source Registration Flow — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Self-service registration form creating records in initial `pending` state with statutory data privacy compliance. |
| **Files** | `app/domains/sources/router.py`, `app/domains/sources/tools.py`, `register_form.html` |
| **Prerequisites** | 1.1 |
| **Done Criteria** | Submitting the registration form creates a new source record with `status='pending'` |

---

#### 1.3 — Public Source Profile View — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Dedicated public profile displaying contact metadata, verification badge (`verified` or `pending`), and active listings. |
| **Files** | `app/domains/sources/templates/source_profile.html`, `app/domains/sources/tools.py` |
| **Prerequisites** | 1.1 |
| **Done Criteria** | `GET /sources/{id}` renders public details and lists associated sterilization campaigns and adoptable animals |

---

### 💚 Pillar 2: Sterilization (Campaigns & Fixed Points) — COMPLETED

#### 2.1 — Campaign and Fixed Point Data Models — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Relational models for `campaigns` (time-bounded mobile events) and `fixed_points` (permanent municipal clinics). |
| **Files** | `app/domains/sterilization/models.py`, Alembic revisions |
| **Prerequisites** | 0.3, 1.1 |
| **Done Criteria** | Tables `campaigns` and `fixed_points` instantiated with coordinates and foreign key constraints |

---

#### 2.2 — Query and Filtering Services — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Search utilities filtering by municipality, target species (`canino`, `felino`), date window, and active status. |
| **Files** | `app/domains/sterilization/tools.py` |
| **Prerequisites** | 2.1 |
| **Done Criteria** | `find_nearby_campaigns(db, "Bogotá, D.C.", ["canino"])` retrieves matching active records |

---

#### 2.3 — Asynchronous Search Interface with HTMX — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Interactive search interface updating campaign cards and map pins dynamically without full page reloads. |
| **Files** | `app/domains/sterilization/router.py`, `index.html`, `map_results.html` |
| **Prerequisites** | 2.2 |
| **Done Criteria** | Changing municipality or species triggers `hx-get` and swaps `#results` smoothly |

---

#### 2.4 — Leaflet Map with Geographic Pins — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Client-side map rendering campaign markers from structured `data-lat` and `data-lng` DOM attributes. |
| **Files** | `app/domains/sterilization/templates/index.html`, `map_results.html` |
| **Prerequisites** | 2.3 |
| **Done Criteria** | Search results populate interactive map pins with click-to-view popups |

---

#### 2.5 — Campaign Detail View — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Detailed view presenting operating hours, capacity, booking URL, requirements, and fresh status indicators. |
| **Files** | `app/domains/sterilization/templates/campaign_detail.html` |
| **Prerequisites** | 2.3 |
| **Done Criteria** | `GET /sterilization/campaigns/{id}` renders complete campaign dossier and interactive location map |

---

### 💛 Pillar 3: Adoption Animals — COMPLETED

#### 3.1 — Animal Profile Data Model — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Relational `animal_profiles` table tracking species, age, sterilization status, adoption state, and media URLs. |
| **Files** | `app/domains/animals/models.py`, Alembic revisions |
| **Prerequisites** | 0.3, 1.1 |
| **Done Criteria** | Database table instantiated with foreign key link to hosting `sources` |

---

#### 3.2 — Profile Ingestion and Photo Storage — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Admin-gated ingestion form supporting multipart photo uploads to Cloudflare R2 object storage. |
| **Files** | `app/domains/animals/router.py`, `app/domains/animals/tools.py`, `profile_form.html` |
| **Prerequisites** | 3.1 |
| **Done Criteria** | Profile creation persists animal attributes and generates verified public photo URL |

---

#### 3.3 — Pet Catalog and Detailed Profile Views — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Responsive catalog with multi-attribute filtering (species, size, municipality, adoption status). |
| **Files** | `app/domains/animals/templates/profile_list.html`, `profile_detail.html` |
| **Prerequisites** | 3.2 |
| **Done Criteria** | Users can search, filter, and inspect detailed pet profiles and shelter contacts |

---

#### 3.4 — Adoption Status Lifecycle via PIN — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Workflow allowing authorized sources to mark pets as `adopted` using their secure 4-digit PIN. |
| **Files** | `app/domains/animals/tools.py`, `app/domains/animals/router.py` |
| **Prerequisites** | 3.1, 4.2 |
| **Done Criteria** | Providing valid PIN transitions pet status from `available` to `adopted` |

---

### 🩷 Pillar 4: Community Updates and Governance — COMPLETED

#### 4.1 — Community Update Relational Model — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Relational `community_updates` table storing reports (`confirmed`, `full`, `cancelled`, `wrong_info`) and vote tallies. |
| **Files** | `app/domains/community/models.py`, Alembic revisions |
| **Prerequisites** | 0.3, 2.1, 3.1 |
| **Done Criteria** | Table instantiated with exclusivity constraint (linked either to `campaign_id` OR `animal_id`) |

---

#### 4.2 — Cryptographic PIN Generation and Delivery — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Secure 4-digit PIN generation using `secrets.randbelow`, bcrypt hashing, and async SMTP dispatch. |
| **Files** | `app/domains/community/tools.py`, `app/shared/security.py`, `app/shared/email.py` |
| **Prerequisites** | 0.2, 4.1 |
| **Done Criteria** | Creating campaigns or pet profiles generates a PIN and schedules background email delivery |

---

#### 4.3 — Citizen Update Reporting Interface — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Public modal/form allowing citizens to submit updates with mandatory PIN verification. |
| **Files** | `app/domains/community/router.py`, `update_form.html`, `update_confirmation.html` |
| **Prerequisites** | 4.2 |
| **Done Criteria** | Validating the correct PIN creates a `CommunityUpdate` record |

---

#### 4.4 — Community Consensus Voting — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Community voting mechanism backed by Valkey rate limiting to validate or challenge pending reports. |
| **Files** | `app/domains/community/router.py`, `app/domains/community/tools.py`, `vote_status.html` |
| **Prerequisites** | 4.3 |
| **Done Criteria** | Reaching `COMMUNITY_VOTE_THRESHOLD` automatically updates the authoritative resource status |

---

### 🤍 Pillar 5: Shelter Verification — COMPLETED

#### 5.1 — Verification Audit Models — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Relational tables `verification_requests`, `visits`, and `checklist_results` for tracking shelter audits. |
| **Files** | `app/domains/verification/models.py`, Alembic revisions |
| **Prerequisites** | 0.3, 1.1 |
| **Done Criteria** | Schema instantiated with relational cascade policies across audits and checklist results |

---

#### 5.2 — Veterinary Audit Checklist System — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Administrative interface allowing veterinarians to record on-site or remote audits across regulatory criteria. |
| **Files** | `app/domains/verification/router.py`, `app/domains/verification/tools.py`, `checklist_form.html` |
| **Prerequisites** | 5.1 |
| **Done Criteria** | All criteria passing advances source status from `pending` to `verified` |

---

### 🟣 Pillar 6: Authentication & Administrative Security — COMPLETED

#### 6.1 — Admin Authentication & Token Management — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Single-administrator authentication via `bcrypt` password verification, PyJWT tokens, and `httpOnly` secure cookies. |
| **Files** | `app/domains/auth/router.py`, `app/domains/auth/rate_limit.py`, `app/shared/security.py` |
| **Prerequisites** | 0.1, 0.4 |
| **Done Criteria** | Secure login, logout, protected mutations, and database metrics dashboard |

---

#### 6.2 — Rate Limiting Infrastructure — COMPLETED

| Field | Details |
|-------|---------|
| **Description** | Valkey-backed IP rate limiter protecting login endpoints (5 attempts/min) and voting actions (1 vote/5 min). |
| **Files** | `app/domains/auth/rate_limit.py`, `app/shared/cache.py` |
| **Prerequisites** | Valkey container |
| **Done Criteria** | Excess requests trigger HTTP 429; graceful fallback if Valkey is unreachable |

---

## 🚫 Explicitly Out of Scope for Phase 1 (MVP)

| Feature | Justification |
|---------|---------------|
| Donation processing / Payment gateways | High legal/accounting liability; project core is strictly open data |
| In-app user chat / Direct messaging | Excessive complexity with negligible MVP value |
| WhatsApp Cloud API integration | Recurring SaaS API costs with zero initial budget |
| General public user account registration | Unnecessary; cryptographic PIN workflow covers decentralized record ownership |
| Master Shelter PIN | Post-MVP: In V1, moderation and community voting mitigate spoofing risks |
| Public impact analytics dashboard | Post-MVP: Requires substantial aggregated historical data |
| Public REST API consumers | Post-MVP: Will be exposed after data ingestion reaches geographic scale |

---

## 📊 Core Quality Metrics

| Metric | Target | Measurement | Status |
|--------|--------|-------------|--------|
| **Automated Test Coverage** | 100% Core Passes | `pytest` test suite across all domains | ✅ 134/134 passing |
| **Static Type Safety** | 0 Type Errors | `mypy --strict` across backend and tests | ✅ 0 errors |
| **Code Style & Linting** | 0 Linter Warnings | `ruff check` and `ruff format --check` | ✅ Clean |
| **Data Freshness Policy** | ≤ 5 Days | Flag campaigns older than 5 days as unconfirmed | ✅ Operational |
| **Consensus Threshold** | ≥ 5 Votes | Community votes needed to override status | ✅ Operational |

---

## 📁 Clean Repository Layout

```
sos-animales/
├── app/
│   ├── main.py                  # FastAPI entry point, lifespan, route mounting
│   ├── config.py                # Pydantic v2 application settings
│   ├── database.py              # Async SQLAlchemy engine and session dependency
│   ├── domains/
│   │   ├── auth/                # Admin auth, JWT tokens, IP rate limiting
│   │   ├── sterilization/       # Campaigns and permanent fixed points
│   │   ├── animals/             # Adoption profiles and media management
│   │   ├── sources/             # Shelter and foundation entities
│   │   ├── community/           # PIN verification, reporting, and voting
│   │   └── verification/        # Veterinary audits and checklist results
│   ├── shared/                  # Common utilities (geo, cache, email, security)
│   └── static/                  # Responsive CSS, icons, and JavaScript assets
├── data/colombia/               # DIVIPOLA geographic seed catalogs (departments & municipalities)
├── migrations/                  # Alembic asynchronous database revisions
├── scripts/                     # Helper CLI scripts (admin password hasher, geo data updater)
├── seed/                        # Idempotent database seed loader
├── tests/                       # Unit, integration, and chaos resilience test suites (134 tests)
├── Makefile                     # Standard developer commands (dev, test, check, migrate, up)
├── pyproject.toml               # Python project dependencies and tool configurations
├── README.md                    # Primary user and onboarding guide (Spanish)
└── ROADMAP.md                   # Technical specifications and operational backlog (English)
```

---

## 📌 Technical Observations & Non-Blocking Backlog

> **Documented Operational Observations (Non-Blocking / Post-Audit Maintenance):**
>
> During the comprehensive Phase 3 test refactoring and resilience auditing, the following items were observed. None of these items block production execution, CI/CD pipelines, or deployment, but they are cataloged here for subsequent routine maintenance:

1. **Starlette TestClient Deprecation Warning (`StarletteDeprecationWarning`)**
   - **Context**: During integration test runs, Starlette emits: `Using httpx with starlette.testclient is deprecated; install httpx2 instead`.
   - **Impact**: Zero impact on test outcomes or production runtime (Starlette `TestClient` is only used inside test fixtures).
   - **Resolution Plan**: Migrate `TestClient` references to native asynchronous `httpx.AsyncClient(transport=ASGITransport(app=app))` or adopt `httpx2` once officially standardized.
   - **Severity**: *Info / Non-Blocking*.

2. **SQLAlchemy Connection Deassociation Warning (`SAWarning`)**
   - **Context**: During asynchronous Pytest fixture teardown, SQLAlchemy occasionally logs: `SAWarning: transaction already deassociated from connection`.
   - **Impact**: Cosmetic warning during fixture cleanup; database transactions are correctly committed or rolled back in all tests.
   - **Resolution Plan**: Refine the async session generator in `tests/conftest.py` to ensure explicit closing of nested connection handles prior to engine disposal.
   - **Severity**: *Info / Non-Blocking*.

3. **Python 3.12 Unraisable Teardown Coroutine Warning (`RuntimeWarning`)**
   - **Context**: When rapid test suites terminate, Python 3.12 logs an unraisable exception: `RuntimeWarning: coroutine 'Connection._cancel' was never awaited`.
   - **Impact**: Occurs solely when `asyncpg` background task pools cancel idle connection keep-alive loops upon Pytest process exit.
   - **Resolution Plan**: Explicitly await `engine.dispose()` within an async session-scoped fixture teardown hook.
   - **Severity**: *Info / Non-Blocking*.

4. **SRE Chaos Query Timeout Enforcement via Session Setting**
   - **Context**: The resilience chaos test simulates database statement timeouts by injecting `SET statement_timeout = '10ms'`.
   - **Impact**: The test accurately proves circuit-breaking and timeout error handling, but depends on PostgreSQL session-level configuration support.
   - **Resolution Plan**: Supplement session-level timeout simulations with network-level fault injection using toxiproxy or mock async socket delays in future end-to-end chaos suites.
   - **Severity**: *Info / Non-Blocking*.
