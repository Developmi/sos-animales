"""SQLAlchemy model for the sources domain.

- Source: foundation, shelter, or rescuer with pending/verified status.
  Stores name, type (official/verified_shelter/community),
  municipality, department, contact channels, and verification timestamp.

The verified status is reached after veterinary audit. While pending,
public views display an unverified advisory banner.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Source(Base):  # type: ignore[misc]
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # official, verified_shelter, community
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    municipality: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Source id={self.id} name='{self.name}' type='{self.type}' status='{self.status}'>"
