"""SQLAlchemy models for the sterilization domain.

- Campaign: specific sterilization event with dates, species,
  capacity, requirements, and status (scheduled/full/completed/cancelled).
- FixedPoint: permanent location (veterinary clinic, mobile unit) with schedule,
  accepted species, fee status, and requirements.

Both models include last_confirmed_at tracking for the freshness policy.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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


class Campaign(Base):  # type: ignore[misc]
    """Specific sterilization campaign events."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    municipality: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Accepted species, e.g.: ['canino', 'felino']
    species: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)

    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    booking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status: scheduled, full, completed, cancelled
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)

    # bcrypt hash of the 4-digit management PIN
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    last_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Data Governance (SDD-07) ---
    data_origin: Mapped[str] = mapped_column(String(30), default="source_submitted")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    __table_args__ = (Index("ix_campaigns_status_starts_at", "status", "starts_at"),)

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} title='{self.title}' status='{self.status}'>"


class FixedPoint(Base):  # type: ignore[misc]
    """Permanent sterilization points (clinics, recurring mobile centers)."""

    __tablename__ = "fixed_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    municipality: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    schedule_text: Mapped[str] = mapped_column(Text, nullable=False)
    species: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Data Governance (SDD-07) ---
    data_origin: Mapped[str] = mapped_column(String(30), default="source_submitted")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    def __repr__(self) -> str:
        return f"<FixedPoint id={self.id} name='{self.name}' municipality='{self.municipality}'>"
