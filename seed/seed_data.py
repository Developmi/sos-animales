"""Carga de datos de prueba para desarrollo local.

Ejecutar con: uv run python -m seed

Requiere PostgreSQL corriendo con las migraciones aplicadas.
Carga datos geográficos de Colombia desde data/colombia/*.json.
Opcionalmente inserta campañas de prueba si hay fuentes registradas.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.domains.sources.models import Source
from app.domains.sterilization.models import Campaign
from app.domains.verification.tools import create_verification_request, schedule_visit
from app.shared.models.location import Department, Municipality

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "colombia"

# Cantidades esperadas del seed estático
_EXPECTED_DEPARTMENTS = 33
_EXPECTED_MUNICIPALITIES = 1123


async def _load_json(filename: str) -> list[dict[str, object]]:
    """Lee un archivo JSON del directorio data/colombia."""
    path = DATA_DIR / filename
    if not path.exists():
        print(
            f"  ⚠️  No se encuentra {filename}. Ejecutá scripts/fetch_colombia_data.py"
        )
        return []
    with open(path, encoding="utf-8") as f:
        return cast("list[dict[str, object]]", json.load(f))


async def _clear_location_data(db: AsyncSession) -> None:
    """Borra datos geográficos respetando FKs: municipios primero, luego dptos."""
    await db.execute(sa_delete(Municipality))
    await db.execute(sa_delete(Department))
    await db.commit()


async def load_departments(db: AsyncSession) -> None:
    """Carga departamentos desde JSON. Si la cantidad no coincide, recarga."""
    actual = await db.scalar(select(func.count(Department.id))) or 0
    if actual == _EXPECTED_DEPARTMENTS:
        print(f"  ↪ {actual} departamentos ya existen (cantidad esperada), saltando.")
        return

    if actual > 0:
        print("  ↪ Recargando datos geográficos (departamentos y municipios)...")
        await _clear_location_data(db)

    data = await _load_json("departments.json")
    if not data:
        return

    db.add_all(Department(id=d["id"], name=d["name"]) for d in data)
    await db.commit()
    print(f"  ✅ {len(data)} departamentos cargados.")


async def load_municipalities(db: AsyncSession) -> None:
    """Carga municipios desde JSON usando upsert (no destructivo)."""
    actual = await db.scalar(select(func.count(Municipality.id))) or 0
    if actual == _EXPECTED_MUNICIPALITIES:
        print(f"  ↪ {actual} municipios ya existen (cantidad esperada), saltando.")
        return

    if actual == 0:
        # Bulk load para tabla vacía
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
        print(f"  ✅ {len(data)} municipios cargados.")
        return

    # Upsert: inserta o actualiza sin borrar datos existentes
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
    print(f"  ✅ {len(data)} municipios sincronizados (upsert).")


async def _seed_demo_data(db: AsyncSession) -> None:
    """Inserta datos de prueba solo si no existen aún (idempotente)."""
    # Verificar si ya hay campañas de prueba
    existing = await db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.title.ilike("%Jornada Zoonosis%")
        )
    )
    if existing and existing > 0:
        print("  ↪ Datos de prueba ya existen, saltando.")
        return

    result = await db.execute(select(Source).limit(1))
    source = result.scalar_one_or_none()
    if not source:
        print("\nℹ️  No hay fuentes. Creando fuente de prueba primero...")
        source = Source(
            name="Fundación SOS Animales Demo",
            type="verified_shelter",
            status="verified",
            municipality="bogota",
            department="bogota",
            contact_email="demo@sos-animales.org",
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        print(f"  ✅ Fuente demo creada (id={source.id})")

    print("  🧪 Insertando campañas de prueba...")

    camp1 = Campaign(
        source_id=source.id,
        title="Gran Jornada Zoonosis - Kennedy",
        municipality="bogota",
        lat=4.6300,
        lng=-74.1500,
        starts_at=datetime.now() + timedelta(days=3),
        species=["canino", "felino"],
        is_free=True,
        status="scheduled",
    )
    camp2 = Campaign(
        source_id=source.id,
        title="Esterilización a Bajo Costo - El Poblado",
        municipality="medellin",
        lat=6.2088,
        lng=-75.5678,
        starts_at=datetime.now() + timedelta(days=10),
        species=["felino"],
        is_free=False,
        status="scheduled",
    )
    db.add_all([camp1, camp2])
    await db.commit()
    print("  ✅ Campañas de prueba insertadas.")

    # Source dudosa + visita de rechazo
    source_dudosa = Source(
        name="Fundación Dudosa",
        type="community",
        status="pending",
        municipality="cali",
        department="valle",
        contact_email="dudosa@test.com",
    )
    db.add(source_dudosa)
    await db.commit()
    await db.refresh(source_dudosa)

    req_ok = await create_verification_request(db, source.id)
    await schedule_visit(
        db,
        req_ok.id,
        "presencial",
        datetime.now(UTC).replace(tzinfo=None),
        "Inspector de prueba",
    )
    req_fail = await create_verification_request(db, source_dudosa.id)
    visit_fail = await schedule_visit(
        db,
        req_fail.id,
        "remota",
        datetime.now(UTC).replace(tzinfo=None),
        "Inspector Riguroso",
    )
    print(f"  ⚠️  Visita para RECHAZAR agendada con ID: {visit_fail.id}")
    print("  ✅ Datos de prueba listos.")


async def seed_data() -> None:
    """Inserta datos geográficos y de prueba (idempotente)."""
    async with AsyncSessionLocal() as db:
        print("📍 Cargando datos geográficos de Colombia...")
        await load_departments(db)
        await load_municipalities(db)

        print("\n🧪 Datos de prueba...")
        await _seed_demo_data(db)

        print("\n✅ ¡Seed completado con éxito!")


if __name__ == "__main__":
    asyncio.run(seed_data())
