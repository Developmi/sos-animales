"""SQLAlchemy model for CommunityUpdate.

- campaign_id / animal_id: exclusive foreign key to the reported entity (XOR constraint).
- update_type: str — 'confirmed' | 'full' | 'cancelled' | 'wrong_info' | 'adopted' | 'in_treatment'.
- votes: int — community consensus vote counter.
- created_at: timestamp.

The consensus voting threshold is configured via .env (COMMUNITY_VOTE_THRESHOLD, default 3-5).
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommunityUpdate(Base):  # type: ignore[misc]
    __tablename__ = "community_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # XOR target: must reference a campaign OR an animal profile, never both
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id"), nullable=True, index=True
    )
    animal_id: Mapped[int | None] = mapped_column(
        ForeignKey("animal_profiles.id"), nullable=True, index=True
    )

    # Update types: 'confirmed', 'full', 'cancelled', 'wrong_info', 'adopted', 'in_treatment'
    update_type: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Community vote counter
    votes: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    # Database-level integrity constraint enforcing exclusive XOR targeting
    __table_args__ = (
        CheckConstraint(
            "(campaign_id IS NOT NULL AND animal_id IS NULL) OR "
            "(campaign_id IS NULL AND animal_id IS NOT NULL)",
            name="check_single_target",
        ),
    )
