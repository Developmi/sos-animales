# Contributing to SOS Animales

## How to Propose a New Source

1. Open an issue with the foundation or shelter name.
2. Include the physical address, official contact info, and social media links.
3. The team will coordinate a two-tier veterinary audit.

## How to Open a Pull Request

1. Ensure your code passes all quality gates: `make check`.
2. Include comprehensive unit and integration tests for new functionality.
3. Keep pull requests focused on a single change or feature.

## Code Standards

- **Linter & Formatter**: `ruff` (zero warnings allowed).
- **Static Typing**: `mypy --strict` on all new code.
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

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 License.
