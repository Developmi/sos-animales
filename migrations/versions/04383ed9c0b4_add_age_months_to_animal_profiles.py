"""add_age_months_to_animal_profiles

Revision ID: 04383ed9c0b4
Revises: e48a09d456f7
Create Date: 2026-10-20 22:14:09.310420

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "04383ed9c0b4"
down_revision: Union[str, Sequence[str], None] = "e48a09d456f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "animal_profiles",
        sa.Column("age_months", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("animal_profiles", "age_months")
