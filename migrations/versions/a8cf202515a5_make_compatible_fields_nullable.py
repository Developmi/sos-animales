"""make_compatible_fields_nullable

Revision ID: a8cf202515a5
Revises: d87a839d50d5
Create Date: 2026-07-08 22:10:23.946484

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8cf202515a5"
down_revision: Union[str, Sequence[str], None] = "d87a839d50d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "animal_profiles",
        "compatible_ninos",
        existing_type=sa.Boolean(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "animal_profiles",
        "compatible_otros_animales",
        existing_type=sa.Boolean(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.alter_column(
        "animal_profiles",
        "compatible_ninos",
        existing_type=sa.Boolean(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "animal_profiles",
        "compatible_otros_animales",
        existing_type=sa.Boolean(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )
