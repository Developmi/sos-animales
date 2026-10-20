"""Download departments and municipalities data from API-Colombia.

Extracts only required fields:
- Department: {id, name}
- Municipality: {id, name, departmentId}

Usage: uv run python scripts/fetch_colombia_data.py

Output files are persisted to data/colombia/ as JSON.
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api-colombia.com/api/v1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "colombia"


async def fetch_json(endpoint: str) -> list[dict[str, Any]]:
    """Fetch raw data from an API-Colombia endpoint."""
    url = f"{API_BASE}/{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return cast("list[dict[str, Any]]", response.json())


def extract_departments(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract id and name fields from departments."""
    return [{"id": d["id"], "name": d["name"]} for d in raw]


def extract_municipalities(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract id, name, and departmentId from municipalities."""
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "departmentId": m["departmentId"],
        }
        for m in raw
    ]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Departments
    logger.info("Downloading departments...")
    raw_departments = await fetch_json("Department")
    departments = extract_departments(raw_departments)
    departments.sort(key=lambda d: d["name"])

    dept_path = DATA_DIR / "departments.json"
    dept_path.write_text(
        json.dumps(departments, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"✅ {len(departments)} departments saved to {dept_path}")

    # 2. Municipalities
    logger.info("Downloading municipalities (may take a few seconds)...")
    raw_cities = await fetch_json("City")
    municipalities = extract_municipalities(raw_cities)
    # Group by department for consistent sorting
    municipalities.sort(key=lambda m: (m["departmentId"], m["name"]))

    mun_path = DATA_DIR / "municipalities.json"
    mun_path.write_text(
        json.dumps(municipalities, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"✅ {len(municipalities)} municipalities saved to {mun_path}")

    logger.info("🎯 Colombia geographic dataset successfully updated!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
