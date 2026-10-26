"""TDD Contract Tests for Single Responsibility Principle (SRP) in `seed/`.

Verifies:
1. `seed/colombia_geo.py` has zero dependencies on domain fixtures (sources, sterilization, verification)
   and only loads/synchronizes Colombian departments and municipalities.
2. `seed/demo_fixtures.py` handles synthetic demo fixtures independently.
3. `seed/__main__.py` runs ONLY `seed_colombia_geo()` by default (`python -m seed`),
   and runs `seed_demo_fixtures()` ONLY when `--demo` is explicitly passed (`python -m seed --demo`).
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_seed_cli_default_runs_only_colombia_geo() -> None:
    """Default `python -m seed` (used by scripts/entrypoint.sh) MUST NOT seed demo fixtures."""
    from seed.__main__ import async_main

    with (
        patch("seed.__main__.seed_colombia_geo", new_callable=AsyncMock) as mock_geo,
        patch("seed.__main__.seed_demo_fixtures", new_callable=AsyncMock) as mock_demo,
    ):
        await async_main([])
        mock_geo.assert_awaited_once()
        mock_demo.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_cli_demo_flag_runs_both_geo_and_demo_fixtures() -> None:
    """Explicit `python -m seed --demo` runs both Colombia geo seed and demo fixtures."""
    from seed.__main__ import async_main

    with (
        patch("seed.__main__.seed_colombia_geo", new_callable=AsyncMock) as mock_geo,
        patch("seed.__main__.seed_demo_fixtures", new_callable=AsyncMock) as mock_demo,
    ):
        await async_main(["--demo"])
        mock_geo.assert_awaited_once()
        mock_demo.assert_awaited_once()


def test_colombia_geo_module_has_strict_single_responsibility() -> None:
    """`seed.colombia_geo` must not import domain models (Source, Campaign, Visit)."""
    import inspect

    from seed import colombia_geo

    source_code = inspect.getsource(colombia_geo)
    assert "app.domains.sources" not in source_code
    assert "app.domains.sterilization" not in source_code
    assert "app.domains.verification" not in source_code
    assert hasattr(colombia_geo, "load_departments")
    assert hasattr(colombia_geo, "load_municipalities")
    assert hasattr(colombia_geo, "seed_colombia_geo")


def test_demo_fixtures_module_is_isolated() -> None:
    """`seed.demo_fixtures` exposes `seed_demo_fixtures` and `populate_demo_data`."""
    from seed import demo_fixtures

    assert hasattr(demo_fixtures, "seed_demo_fixtures")
    assert hasattr(demo_fixtures, "populate_demo_data")
