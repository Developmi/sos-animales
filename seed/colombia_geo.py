"""Single-responsibility seed module for official Colombian DIVIPOLA territorial divisions.

Loads and synchronizes Colombia's 33 departments and 1,123 municipalities from
static JSON snapshots (`data/colombia/departments.json` and `data/colombia/municipalities.json`).
Safe and idempotent for production container startup (`scripts/entrypoint.sh`).
"""

import json
from pathlib import Path
from typing import cast

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.shared.models.location import Department, Municipality

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "colombia"

_EXPECTED_DEPARTMENTS = 33
_EXPECTED_MUNICIPALITIES = 1123


async def _load_json(filename: str) -> list[dict[str, object]]:
    """Read a static JSON dataset from `data/colombia/`."""
    path = DATA_DIR / filename
    if not path.exists():
        print(
            f"  ⚠️  Missing {filename}. Run scripts/fetch_colombia_data.py to regenerate."
        )
        return []
    with open(path, encoding="utf-8") as f:
        return cast("list[dict[str, object]]", json.load(f))


async def _clear_location_data(db: AsyncSession) -> None:
    """Clear territorial data respecting foreign-key order (municipalities first, then departments)."""
    await db.execute(sa_delete(Municipality))
    await db.execute(sa_delete(Department))
    await db.commit()


async def load_departments(db: AsyncSession) -> None:
    """Load Colombian departments from JSON if count differs from expected catalog size."""
    actual = await db.scalar(select(func.count(Department.id))) or 0
    if actual == _EXPECTED_DEPARTMENTS:
        print(f"  ↪ {actual} departments already present (expected count), skipping.")
        return

    if actual > 0:
        print(
            "  ↪ Reloading Colombian geographic catalog (departments & municipalities)..."
        )
        await _clear_location_data(db)

    data = await _load_json("departments.json")
    if not data:
        return

    db.add_all(Department(id=d["id"], name=d["name"]) for d in data)
    await db.commit()
    print(f"  ✅ {len(data)} departments loaded.")


async def load_municipalities(db: AsyncSession) -> None:
    """Load Colombian municipalities from JSON using non-destructive PostgreSQL upsert."""
    actual = await db.scalar(select(func.count(Municipality.id))) or 0
    if actual == _EXPECTED_MUNICIPALITIES:
        print(
            f"  ↪ {actual} municipalities already present (expected count), skipping."
        )
        return

    if actual == 0:
        dept_count = await db.scalar(select(func.count(Department.id))) or 0
        if dept_count == 0:
            data_depts = await _load_json("departments.json")
            if data_depts:
                db.add_all(Department(id=d["id"], name=d["name"]) for d in data_depts)
                await db.commit()

        data = await _load_json("municipalities.json")
        if not data:
            return

        db.add_all(
            Municipality(id=m["id"], name=m["name"], department_id=m["departmentId"])
            for m in data
        )
        await db.commit()
        print(f"  ✅ {len(data)} municipalities loaded.")
        return

    data = await _load_json("municipalities.json")
    if not data:
        return

    for m in data:
        insert_stmt = pg_insert(Municipality).values(
            id=m["id"],
            name=m["name"],
            department_id=m["departmentId"],
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": insert_stmt.excluded.name,
                "department_id": insert_stmt.excluded.department_id,
            },
        )
        await db.execute(stmt)

    await db.commit()
    print(f"  ✅ {len(data)} municipalities synchronized (upsert).")


async def seed_colombia_geo() -> None:
    """Ensure Colombia's official departments and municipalities exist in PostgreSQL."""
    async with AsyncSessionLocal() as db:
        print("📍 Synchronizing Colombian geographic reference data...")
        await load_departments(db)
        await load_municipalities(db)
        print("✅ Colombian geographic reference data is ready.")
