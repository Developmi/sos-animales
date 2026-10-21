"""Pure business logic functions for the animals domain.

- create_animal_profile: creates an animal profile linked to a shelter/rescuer source.
- list_animals_by_filters: search by municipality, species, and adoption status.
- get_animal_detail: full profile details joined with responsible source organization.
- mark_as_adopted: updates status to adopted upon valid PIN verification.
"""

import uuid
import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
from sqlalchemy import select
from datetime import datetime, timezone

from app.config import settings
from app.shared.security import generate_pin, hash_pin, verify_pin
from app.domains.sources.models import Source
from app.domains.animals.models import AnimalProfile

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def validate_image_file(file: UploadFile) -> None:
    """Validate that file exists, is an image, and does NOT exceed 5MB.

    Fast rejection before any network or S3/R2 upload.
    Raises ValueError with a user-friendly message if oversized or invalid.
    """
    if not file or not file.filename:
        return

    # Check MIME type
    if file.content_type and not file.content_type.startswith("image/"):
        raise ValueError(
            f"El archivo '{file.filename}' no es una imagen válida (tipo detectado: {file.content_type})."
        )

    # Calculate file size
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)

    if size > MAX_IMAGE_SIZE_BYTES:
        size_mb = size / (1024 * 1024)
        raise ValueError(
            f"El archivo '{file.filename}' pesa {size_mb:.1f}MB, superando el límite máximo permitido de 5MB."
        )


async def upload_photo_to_r2(file: UploadFile) -> str:
    """Upload photo to Cloudflare R2 (or fallback placeholder when unconfigured).

    If R2_ENDPOINT is configured, uses boto3 S3-compatible API.
    Otherwise, returns via.placeholder.com URL for local development.
    """
    validate_image_file(file)
    filename = file.filename or "unknown_image.jpg"
    file_extension = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    unique_filename = f"{uuid.uuid4()}.{file_extension}"

    # If R2 storage is configured, perform real S3 upload
    if settings.R2_ENDPOINT:
        try:
            import boto3
            from botocore.config import Config as BotoConfig

            s3 = boto3.client(
                "s3",
                endpoint_url=settings.R2_ENDPOINT,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                config=BotoConfig(signature_version="s3v4"),
                region_name="us-east-1",
            )
            file.file.seek(0)
            import asyncio

            await asyncio.to_thread(
                s3.upload_fileobj, file.file, settings.R2_BUCKET_NAME, unique_filename
            )

            public_url = f"{settings.R2_PUBLIC_URL}/{unique_filename}"
            logger.info("📸 Photo uploaded to R2: %s", public_url)
            return public_url

        except ImportError:
            logger.warning(
                "boto3 not installed. Install 'boto3' to enable R2 storage. Using placeholder."
            )
        except Exception as e:
            logger.error("Error uploading to R2: %s", e)
            raise RuntimeError(f"Error uploading to R2: {e}") from e

    # Fallback: placeholder for local development
    fake_url = f"https://via.placeholder.com/600x400.png?text={unique_filename}"
    logger.info("📸 Using placeholder (R2 not configured): %s", fake_url)
    return fake_url


async def upload_multiple_photos(
    files: list[UploadFile], max_files: int = 5
) -> list[str]:
    """Upload up to N photos and return list of URLs. First photo is mandatory."""
    urls: list[str] = []
    for f in files[:max_files]:
        if f.filename:
            url = await upload_photo_to_r2(f)
            urls.append(url)
    return urls


async def create_animal_profile(
    db: AsyncSession, source_id: int, data: dict[str, Any], foto_url: str
) -> dict[str, Any]:
    """Create animal profile entity and return it TOGETHER with the plaintext PIN."""

    existing = await db.execute(
        select(AnimalProfile).where(
            AnimalProfile.name == data["name"],
            AnimalProfile.source_id == source_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Ya existe un animal con ese nombre para esta fuente")

    raw_pin = generate_pin()
    hashed_pin = hash_pin(raw_pin)

    new_animal = AnimalProfile(
        source_id=source_id,
        name=data["name"],
        species=data["species"],
        breed=data.get("breed"),
        age_months=data.get("age_months"),
        age_years=data.get("age_years"),
        size=data.get("size"),
        foto_url=foto_url,
        foto_urls=data.get("foto_urls"),
        is_sterilized=data.get("is_sterilized", False),
        description=data.get("description"),
        municipality=data["municipality"],
        status="available",
        pin_hash=hashed_pin,
        sexo=data.get("sexo"),
        fecha_nacimiento=data.get("fecha_nacimiento"),
        etapa_madurez=data.get("etapa_madurez"),
        condiciones_especiales=data.get("condiciones_especiales"),
        compatible_ninos=data.get("compatible_ninos"),
        compatible_otros_animales=data.get("compatible_otros_animales"),
        microchip=data.get("microchip"),
        data_origin=data.get("data_origin", "source_submitted"),
        source_url=data.get("source_url"),
    )

    db.add(new_animal)
    await db.commit()
    await db.refresh(new_animal)

    return {"animal": new_animal, "raw_pin": raw_pin}


async def mark_as_adopted(db: AsyncSession, animal_id: int, pin: str) -> bool:
    """Verify PIN and update animal status to 'adopted'."""
    result = await db.execute(
        select(AnimalProfile).where(AnimalProfile.id == animal_id)
    )
    animal = result.scalar_one_or_none()

    if not animal or not animal.pin_hash:
        return False

    if verify_pin(pin, animal.pin_hash):
        animal.status = "adopted"
        animal.adopted_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    return False


async def list_animals_by_filters(
    db: AsyncSession,
    municipality: str | None = None,
    species: str | None = None,
    status: str = "available",
    limit: int = 48,
) -> list[AnimalProfile]:
    """Retrieve catalog of animals matching filter criteria."""
    query = select(AnimalProfile).where(AnimalProfile.status == status)

    if municipality:
        query = query.where(AnimalProfile.municipality.ilike(f"%{municipality}%"))
    if species:
        species_normalized = species.lower()
        if species_normalized in ("perro", "perros", "canino"):
            query = query.where(AnimalProfile.species.in_(["canino", "perro"]))
        elif species_normalized in ("gato", "gatos", "felino"):
            query = query.where(AnimalProfile.species.in_(["felino", "gato"]))
        else:
            query = query.where(AnimalProfile.species.ilike(f"%{species}%"))

    query = query.order_by(AnimalProfile.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_animal_detail(db: AsyncSession, animal_id: int) -> dict[str, Any] | None:
    """Full animal profile detail joined with responsible shelter/rescuer source."""
    query = (
        select(AnimalProfile, Source)
        .join(Source, AnimalProfile.source_id == Source.id)
        .where(AnimalProfile.id == animal_id)
    )
    result = await db.execute(query)
    row = result.first()

    if row:
        return {"animal": row.AnimalProfile, "source": row.Source}
    return None
