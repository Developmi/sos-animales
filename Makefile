# ==============================================================================
# SOS Animales Colombia — Enterprise Makefile
# Follows the DevSecOps gold standard: tool pins in tools/versions.mk,
# deterministic binary installation in tools/bin/, multi-layer linting,
# strict test coverage gates, and container security auditing.
# ==============================================================================

include tools/versions.mk

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Paths & Runners
TOOLS := tools/bin
UV := uv run
DOCKER_COMPOSE := docker compose
IMAGE_NAME ?= sos-animales:local
export IMAGE_NAME

.PHONY: help
help: ## Show this help menu with all available targets
	@echo ""
	@echo "🐾 SOS Animales — Operational & DevSecOps Targets"
	@echo "================================================="
	@echo ""
	@echo "Setup & Environment"
	@echo "-------------------"
	@printf "  \033[36m%-20s\033[0m %s\n" "tools" "Install pinned development tools into tools/bin"
	@printf "  \033[36m%-20s\033[0m %s\n" "reinstall" "Force reinstall pinned development tools"
	@printf "  \033[36m%-20s\033[0m %s\n" "doctor" "Diagnose development environment and tool versions"
	@echo ""
	@echo "Quality Assurance & Linters"
	@echo "---------------------------"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint" "Run full multi-layer linter suite (Ruff, Mypy, YAML, Actions, Docker, Zizmor)"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint-python" "Run Ruff code analysis"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint-yaml" "Lint YAML files with yamllint"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint-actions" "Lint GitHub Actions workflows with actionlint"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint-docker" "Lint Dockerfile with hadolint"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint-security" "Scan GitHub Actions for security flaws with zizmor"
	@printf "  \033[36m%-20s\033[0m %s\n" "typecheck" "Run strict static type checking with Mypy"
	@printf "  \033[36m%-20s\033[0m %s\n" "check-format" "Verify code formatting with Ruff without mutating files"
	@printf "  \033[36m%-20s\033[0m %s\n" "format" "Format codebase with Ruff"
	@printf "  \033[36m%-20s\033[0m %s\n" "lint-fix" "Automatically fix safe Ruff linting violations"
	@echo ""
	@echo "Testing & Coverage Gates"
	@echo "------------------------"
	@printf "  \033[36m%-20s\033[0m %s\n" "test" "Execute full test suite with pytest"
	@printf "  \033[36m%-20s\033[0m %s\n" "test-unit" "Run unit tests (isolated, fast, no external services)"
	@printf "  \033[36m%-20s\033[0m %s\n" "test-integration" "Run integration tests with database and services"
	@printf "  \033[36m%-20s\033[0m %s\n" "test-coverage" "Run tests and display statement coverage report"
	@printf "  \033[36m%-20s\033[0m %s\n" "test-coverage-gate" "Enforce strict statement coverage threshold (>= 80%)"
	@printf "  \033[36m%-20s\033[0m %s\n" "test-security" "Run Trivy container vulnerability scan"
	@printf "  \033[36m%-20s\033[0m %s\n" "check" "Run comprehensive QA gate (lint + coverage gate)"
	@echo ""
	@echo "Containers, Build & Operations"
	@echo "------------------------------"
	@printf "  \033[36m%-20s\033[0m %s\n" "docker-build" "Build local application Docker image"
	@printf "  \033[36m%-20s\033[0m %s\n" "compose-config" "Validate docker-compose configuration without side effects"
	@printf "  \033[36m%-20s\033[0m %s\n" "up" "Start all services in background"
	@printf "  \033[36m%-20s\033[0m %s\n" "down" "Stop all running containers"
	@printf "  \033[36m%-20s\033[0m %s\n" "down-v" "Stop containers and purge data volumes"
	@printf "  \033[36m%-20s\033[0m %s\n" "restart" "Restart all containers"
	@printf "  \033[36m%-20s\033[0m %s\n" "ps" "Show container status"
	@printf "  \033[36m%-20s\033[0m %s\n" "logs" "Stream logs from all services"
	@printf "  \033[36m%-20s\033[0m %s\n" "logs-web" "Stream web logs only"
	@printf "  \033[36m%-20s\033[0m %s\n" "logs-db" "Stream db logs only"
	@printf "  \033[36m%-20s\033[0m %s\n" "logs-valkey" "Stream valkey logs only"
	@printf "  \033[36m%-20s\033[0m %s\n" "dev" "Start local dev server with hot-reload"
	@printf "  \033[36m%-20s\033[0m %s\n" "migrate" "Apply pending Alembic migrations"
	@printf "  \033[36m%-20s\033[0m %s\n" "makemigrations" "Generate new Alembic migration revision"
	@printf "  \033[36m%-20s\033[0m %s\n" "seed" "Synchronize official Colombian geographic catalog"
	@printf "  \033[36m%-20s\033[0m %s\n" "seed-demo" "Synchronize geographic catalog and dev demo fixtures"
	@printf "  \033[36m%-20s\033[0m %s\n" "shell-db" "Open interactive psql shell in DB container"
	@printf "  \033[36m%-20s\033[0m %s\n" "clean" "Clean temporary test, cache, and coverage artifacts"
	@echo ""
	@echo "Release Preflight"
	@echo "-----------------"
	@printf "  \033[36m%-20s\033[0m %s\n" "release-ready" "Full pre-push gate (lint + coverage gate + compose + build + security)"
	@echo ""

# ------------------------------------------------------------------------------
# Tooling & Setup
# ------------------------------------------------------------------------------

.PHONY: tools
tools: ## Install pinned development tools into tools/bin
	@ACTIONLINT_VERSION=$(ACTIONLINT_VERSION) \
	HADOLINT_VERSION=$(HADOLINT_VERSION) \
	TRIVY_VERSION=$(TRIVY_VERSION) \
	./tools/install.sh
	@echo "✓ Development tools are ready."

.PHONY: reinstall
reinstall: ## Force reinstall of all development tools
	@REINSTALL=1 $(MAKE) tools
	@echo "✓ Development tools reinstalled."

.PHONY: doctor
doctor: ## Verify development environment and tool versions
	@test -x $(TOOLS)/actionlint || $(MAKE) --no-print-directory tools
	@printf "\n"
	@printf "SOS Animales — Development Environment\n"
	@printf "======================================\n\n"
	@printf "%-18s %s\n" "python" "$$(python3 --version | awk '{print $$2}')"
	@printf "%-18s %s\n" "uv" "$$(uv --version | awk '{print $$2}')"
	@printf "%-18s %s\n" "Docker" "$$(docker version --format '{{.Client.Version}}' 2>/dev/null || echo 'N/A')"
	@printf "%-18s %s\n" "ruff" "$$($(UV) ruff --version | awk '{print $$2}')"
	@printf "%-18s %s\n" "mypy" "$$($(UV) mypy --version | awk '{print $$2}')"
	@printf "%-18s %s\n" "yamllint" "$$($(UV) yamllint --version | awk '{print $$2}')"
	@printf "%-18s %s\n" "zizmor" "$$($(UV) zizmor --version | awk '{print $$2}')"
	@printf "%-18s %s\n" "actionlint" "$$($(TOOLS)/actionlint -version 2>/dev/null | head -1)"
	@printf "%-18s %s\n" "hadolint" "$$($(TOOLS)/hadolint --version 2>/dev/null | awk '{print $$NF}')"
	@printf "%-18s %s\n" "trivy" "$$($(TOOLS)/trivy --version 2>/dev/null | head -1 | awk '{print $$2}')"
	@echo ""

# ------------------------------------------------------------------------------
# Quality Assurance, Linting & Typechecking
# ------------------------------------------------------------------------------

.PHONY: lint-python
lint-python: ## Run Ruff linter
	@echo "==> Python (Ruff)"
	@$(UV) ruff check .
	@echo "✓ Ruff lint passed."

.PHONY: check-format
check-format: ## Verify code formatting with Ruff
	@echo "==> Format check (Ruff)"
	@$(UV) ruff format --check .
	@echo "✓ Format check passed."

.PHONY: format
format: ## Format codebase with Ruff
	@echo "==> Formatting Python files"
	@$(UV) ruff format .
	@echo "✓ Codebase formatted."

.PHONY: lint-fix
lint-fix: ## Automatically fix safe Ruff linting violations
	@echo "==> Fixing safe Ruff violations"
	@$(UV) ruff check --fix .
	@echo "✓ Safe fixes applied."

.PHONY: typecheck
typecheck: ## Run strict static type checking with Mypy
	@echo "==> Typecheck (Mypy)"
	@$(UV) mypy app/ tests/
	@echo "✓ Strict typecheck passed."

.PHONY: lint-yaml
lint-yaml: ## Lint all YAML files
	@echo "==> YAML (yamllint)"
	@$(UV) yamllint .
	@echo "✓ YAML lint passed."

.PHONY: lint-actions
lint-actions: ## Lint GitHub Actions workflows
	@echo "==> GitHub Actions (actionlint)"
	@test -x $(TOOLS)/actionlint || $(MAKE) --no-print-directory tools
	@if [ -d .github/workflows ]; then \
		$(TOOLS)/actionlint; \
	else \
		echo "No .github/workflows directory; skipping actionlint."; \
	fi
	@echo "✓ GitHub Actions lint passed."

.PHONY: lint-docker
lint-docker: ## Lint Dockerfile
	@echo "==> Dockerfile (hadolint)"
	@test -x $(TOOLS)/hadolint || $(MAKE) --no-print-directory tools
	@$(TOOLS)/hadolint --failure-threshold warning Dockerfile
	@echo "✓ Dockerfile lint passed."

.PHONY: lint-security
lint-security: ## Scan GitHub Actions workflows for security issues (zizmor)
	@echo "==> Actions Security (zizmor)"
	@if [ -d .github/workflows ]; then \
		$(UV) zizmor .; \
	else \
		echo "No .github/workflows directory; skipping zizmor."; \
	fi
	@echo "✓ Actions security scan passed."

.PHONY: lint
lint: lint-python check-format typecheck lint-yaml lint-actions lint-docker lint-security ## Run all linters
	@echo ""
	@echo "✓ All multi-layer lint checks passed."

# ------------------------------------------------------------------------------
# Testing & Coverage
# ------------------------------------------------------------------------------

.PHONY: test
test: ## Run full test suite with pytest
	@echo "==> Tests (full pytest suite)"
	@$(UV) pytest
	@echo "✓ Test suite passed."

.PHONY: test-unit
test-unit: ## Run fast unit tests (isolated, no external services)
	@echo "==> Tests (unit)"
	@$(UV) pytest tests/shared/test_security.py tests/shared/test_geo.py tests/shared/test_email.py tests/domains/test_*tools*.py
	@echo "✓ Unit tests passed."

.PHONY: test-integration
test-integration: ## Run integration tests with database and services
	@echo "==> Tests (integration)"
	@$(UV) pytest tests/domains/test_*integration*.py tests/domains/test_routers.py tests/domains/test_public_mutation_flows.py tests/shared/test_sre_resilience.py tests/shared/test_valkey_lifecycle.py tests/test_*.py
	@echo "✓ Integration tests passed."

.PHONY: test-coverage
test-coverage: ## Run tests and display statement coverage report
	@echo "==> Tests (coverage report)"
	@$(UV) pytest --cov=app --cov-report=term-missing
	@echo "✓ Coverage report generated."

.PHONY: test-coverage-gate
test-coverage-gate: ## Enforce strict statement coverage threshold (>= 80%)
	@echo "==> Tests (coverage gate >= 80%)"
	@$(UV) pytest --cov=app --cov-report=term-missing --cov-fail-under=80
	@echo "✓ Coverage threshold gate passed (>= 80%)."

.PHONY: sbom
sbom: ## Generate SPDX & CycloneDX SBOMs and scan with Trivy + OpenVEX
	@echo "==> Supply Chain (SPDX & CycloneDX SBOM + Trivy OpenVEX Scan)"
	@test -x $(TOOLS)/trivy || $(MAKE) --no-print-directory tools
	@docker image inspect $(IMAGE_NAME) >/dev/null 2>&1 || docker build -t $(IMAGE_NAME) .
	@$(TOOLS)/trivy image --format spdx-json --output sbom.spdx.json $(IMAGE_NAME)
	@$(TOOLS)/trivy image --format cyclonedx --output sbom.cdx.json $(IMAGE_NAME)
	@$(TOOLS)/trivy sbom sbom.spdx.json --exit-code 1 --severity HIGH,CRITICAL --vex vex/sos-animales-vex.json
	@echo "✓ SPDX (sbom.spdx.json) & CycloneDX (sbom.cdx.json) SBOMs generated and verified (0 HIGH, 0 CRITICAL)."

.PHONY: test-security
test-security: ## Run Trivy vulnerability scan against container image with OpenVEX governance
	@echo "==> Security (Trivy container scan + OpenVEX)"
	@test -x $(TOOLS)/trivy || $(MAKE) --no-print-directory tools
	@docker image inspect $(IMAGE_NAME) >/dev/null 2>&1 || docker build -t $(IMAGE_NAME) .
	@$(TOOLS)/trivy image --exit-code 1 --severity HIGH,CRITICAL --vex vex/sos-animales-vex.json $(IMAGE_NAME)
	@echo "✓ Trivy container security scan passed with OpenVEX governance (0 HIGH, 0 CRITICAL)."

.PHONY: check
check: lint test-coverage-gate ## Run complete QA gate (all linters + coverage gate)
	@echo ""
	@echo "✓ Full QA check passed."

# ------------------------------------------------------------------------------
# Containers & Docker Compose
# ------------------------------------------------------------------------------

.PHONY: build docker-build
build: docker-build ## Alias for docker-build
docker-build: ## Build the local Docker image
	@echo "==> Docker build"
	@docker build -t $(IMAGE_NAME) .
	@echo "✓ Docker image $(IMAGE_NAME) built successfully."

.PHONY: compose-config
compose-config: ## Validate the docker-compose configuration without side effects
	@echo "==> Compose config"
	@$(DOCKER_COMPOSE) config --quiet
	@echo "✓ Compose configuration is valid."

.PHONY: up
up: ## Start all services (web, db, valkey) in background
	$(DOCKER_COMPOSE) up -d

.PHONY: down
down: ## Stop and remove running containers and networks
	$(DOCKER_COMPOSE) down

.PHONY: down-v
down-v: ## Stop and remove containers, networks, and data VOLUMES (DB Reset)
	$(DOCKER_COMPOSE) down -v

.PHONY: rebuild
rebuild: ## Rebuild the application image and recreate containers
	$(DOCKER_COMPOSE) up -d --build

.PHONY: restart
restart: ## Restart all running containers
	$(DOCKER_COMPOSE) restart

.PHONY: ps
ps: ## Display status and health of project containers
	$(DOCKER_COMPOSE) ps

.PHONY: logs
logs: ## Stream aggregated real-time logs from all services
	$(DOCKER_COMPOSE) logs -f

.PHONY: logs-web
logs-web: ## Stream real-time logs from the web container only
	$(DOCKER_COMPOSE) logs -f web

.PHONY: logs-db
logs-db: ## Stream real-time logs from the PostgreSQL database container
	$(DOCKER_COMPOSE) logs -f db

.PHONY: logs-valkey
logs-valkey: ## Stream real-time logs from the Valkey cache container
	$(DOCKER_COMPOSE) logs -f valkey

# ------------------------------------------------------------------------------
# Local Development & Database Migrations
# ------------------------------------------------------------------------------

.PHONY: dev
dev: ## Start local development server with hot-reload
	$(UV) uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

.PHONY: migrate
migrate: ## Apply pending Alembic migrations to database
	$(UV) alembic upgrade head

.PHONY: makemigrations
makemigrations: ## Generate a new autogenerated Alembic migration revision
	@read -p "Enter migration message: " MSG; \
	$(UV) alembic revision --autogenerate -m "$$MSG"

.PHONY: seed
seed: ## Synchronize official Colombian geographic reference catalog (production-safe)
	$(UV) python -m seed

.PHONY: seed-demo
seed-demo: ## Synchronize geographic catalog plus synthetic demo fixtures (dev/QA only)
	$(UV) python -m seed --demo

.PHONY: shell-db
shell-db: ## Open interactive psql shell inside the PostgreSQL container
	docker exec -it sos_animales_db psql -U user -d sos_animales

.PHONY: clean
clean: ## Remove temporary test, cache, and coverage artifacts
	@rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov sbom.*.json
	@echo "✓ Temporary artifacts cleaned."

# ------------------------------------------------------------------------------
# Release Preflight Gate
# ------------------------------------------------------------------------------

.PHONY: release-ready
release-ready: lint test-coverage-gate compose-config docker-build test-security ## Full pre-push verification gate
	@echo ""
	@echo "================================================="
	@echo "🚀 RELEASE-READY GATE PASSED"
	@echo "All linters, coverage gate, compose config,"
	@echo "image build and container security scans OK."
	@echo "================================================="
