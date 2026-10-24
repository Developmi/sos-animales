"""SQLAlchemy model for AnimalProfile.

- foto_url: str — Public image URL on Cloudflare R2.
- species: str — 'canino' | 'felino' (v1 scope).
- status: str — 'available' | 'adopted' | 'in_treatment'.
- is_sterilized: bool — demographic tracking and health analysis.
- source_id: FK to Source (shelter/rescuer).
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnimalProfile(Base):  # type: ignore[misc]
    __tablename__ = "animal_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'canino' o 'felino'
    breed: Mapped[str | None] = mapped_column(String(100), nullable=True)
    age_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # 'pequeno', 'mediano', 'grande'

    foto_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Additional photos (up to 4). foto_url remains primary photo.
    foto_urls: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    pin_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # bcrypt hash of 4-digit management PIN

    status: Mapped[str] = mapped_column(
        String(20), default="available", index=True
    )  # available, adopted, in_treatment
    is_sterilized: Mapped[bool] = mapped_column(Boolean, default=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    municipality: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # --- Data Governance (SDD-07) ---
    sexo: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # 'macho' / 'hembra'
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    etapa_madurez: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # cachorro/joven/adulto/geronte
    condiciones_especiales: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    compatible_ninos: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    compatible_otros_animales: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    microchip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_origin: Mapped[str] = mapped_column(String(30), default="source_submitted")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    adopted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_animal_profiles_status_created_at", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AnimalProfile id={self.id} name='{self.name}' species='{self.species}' status='{self.status}'>"
