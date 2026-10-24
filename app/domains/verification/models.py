"""SQLAlchemy models for the verification domain.

- VerificationRequest: verification request for a source/shelter entity.
  States: pending, scheduled (visit scheduled), done, rejected.
- ChecklistResult: individual criterion evaluated during veterinary inspection.
- Visit: inspection visit record — on-site (within 2h radius of Bogota) or remote
  (local veterinary partner or virtual session, executing the identical checklist).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VerificationRequest(Base):  # type: ignore[misc]
    """Verification request for an animal shelter or rescue organization."""

    __tablename__ = "verification_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, scheduled, done, rejected
    submitted_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    def __repr__(self) -> str:
        return f"<VerificationRequest id={self.id} source_id={self.source_id} status='{self.status}'>"


class Visit(Base):  # type: ignore[misc]
    """Record of an in-person or remote veterinary inspection visit."""

    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    verification_request_id: Mapped[int] = mapped_column(
        ForeignKey("verification_requests.id"), nullable=False, index=True
    )

    visit_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # presencial, remota
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    visitor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Visit id={self.id} verification_request_id={self.verification_request_id} visit_type='{self.visit_type}'>"


class ChecklistResult(Base):  # type: ignore[misc]
    """Individual criterion result evaluated during a verification visit."""

    __tablename__ = "checklist_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_id: Mapped[int] = mapped_column(
        ForeignKey("visits.id"), nullable=False, index=True
    )

    criterion: Mapped[str] = mapped_column(String(100), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ChecklistResult id={self.id} visit_id={self.visit_id} criterion='{self.criterion}' passed={self.passed}>"
