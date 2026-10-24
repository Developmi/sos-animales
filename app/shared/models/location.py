"""SQLAlchemy models for geographic locations in Colombia.

- Department: departments (32 + Bogota D.C.).
- Municipality: municipalities (~1,122) foreign-keyed to a department.

Populated via static seed (data/colombia/) instead of runtime external API requests.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Department(Base):  # type: ignore[misc]
    """Department of Colombia."""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Department {self.id}: {self.name}>"


class Municipality(Base):  # type: ignore[misc]
    """Municipality of Colombia, associated with a department."""

    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Municipality {self.id}: {self.name} ({self.department_id})>"
