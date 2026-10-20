"""Entry point para ejecutar el seed: uv run python -m seed"""

from seed.seed_data import seed_data

if __name__ == "__main__":
    import asyncio

    asyncio.run(seed_data())
