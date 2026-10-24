# Contributing to SOS Animales

Thank you for your interest in contributing to **SOS Animales**. This project follows the **Developmi** engineering standard and strictly enforces `uv` as its exclusive Python package manager.

## Development Setup

```bash
# 1. Clone and install dependencies using uv (never use pip, poetry, or npm)
git clone https://github.com/Developmi/sos-animales.git
cd sos-animales
uv sync

# 2. Configure local environment from the Single Source of Truth (.env.example)
cp .env.example .env

# 3. Start PostgreSQL 17 and Valkey 8 support containers
docker compose up -d db valkey

# 4. Run database migrations and seed initial Colombia dataset
make migrate
uv run python -m seed

# 5. Verify full quality gate (lint + strict typing + >=80% coverage gate)
make check
```

## How to Propose a New Source

1. Open an issue with the foundation or shelter name.
2. Include the physical address, official contact info, and social media links.
3. The team will coordinate a two-tier veterinary audit.

## Commit Standard

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add dynamic foundation selector to animal publishing form
fix: reset failed PIN attempts in Valkey after valid adoption
docs: expand README with Developmi architecture and configuration tables
chore: bump ruff to 0.15.20
```

Types: `feat` · `fix` · `docs` · `chore` · `refactor` · `perf` · `test`

## Branch Naming

```text
feat/short-description
fix/issue-number-description
docs/update-readme
chore/bump-dependencies
```

## Pull Request Process

1. Fork the repository and create your feature branch from `main`.
2. Ensure all tests and coverage gates pass: `uv run pytest` or `make test-coverage-gate`.
3. Ensure multi-layer linting and strict typing pass: `make lint` (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app/ tests/`).
4. Ensure your code passes the unified quality gate: `make check`.
5. Include comprehensive unit and integration tests for new functionality (TDD RED → GREEN → REFACTOR).
6. Keep pull requests focused on a single change or feature.
7. Update documentation if your change affects public behavior or environment variables.
8. Open a PR with a clear title following the commit standard. A maintainer will review within 5 business days.

## Code Standards

- **Package Manager**: `uv` exclusively (`uv.lock`). Never use `pip`, `poetry`, `npm`, or `yarn`.
- **Linter & Formatter**: `ruff` (zero warnings allowed).
- **Static Typing**: `mypy --strict` on all code (`app/` and `tests/`).
- **Documentation**: English docstrings on all modules, classes, and public functions.
- **Domain Architecture**: Modular domain isolation (`models.py`, `schemas.py`, `tools.py`, `router.py`).
- Pure business logic in `tools.py` decoupled from HTTP transports.

## Project Scope Constraints

This project strictly does NOT manage:
- Donations, payments, or money transfers.
- General public user accounts.
- Direct user chat or messaging systems.
- Commercial WhatsApp Cloud APIs.

Contributions touching these topics will be declined.

## Reporting Issues

Use [GitHub Issues](https://github.com/Developmi/sos-animales/issues). Include:
- Steps to reproduce
- Expected vs. actual behavior
- Environment (OS, Python version, `uv --version`, Docker version)

## Code of Conduct

This project adheres to the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for full details.

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](./LICENSE).
