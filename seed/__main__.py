"""CLI entrypoint for database seeding (`python -m seed`).

By default (`python -m seed`), ONLY official Colombian geographic data
(33 departments and 1,123 municipalities) is synchronized.
Pass `--demo` (`python -m seed --demo`) to additionally load synthetic demo fixtures
for local development and QA.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from seed.colombia_geo import seed_colombia_geo
from seed.demo_fixtures import seed_demo_fixtures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the seed runner."""
    parser = argparse.ArgumentParser(
        prog="python -m seed",
        description="Synchronize Colombian geographic reference data (and optional dev demo fixtures).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Also insert synthetic demo shelters, campaigns, and verification visits (dev/QA only).",
    )
    return parser.parse_args(argv)


async def async_main(argv: Sequence[str] | None = None) -> None:
    """Execute seed workflow according to CLI flags."""
    args = parse_args(argv)
    await seed_colombia_geo()
    if args.demo:
        await seed_demo_fixtures()


def main() -> None:
    """Synchronous CLI entrypoint."""
    asyncio.run(async_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
