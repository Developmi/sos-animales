"""add_data_governance_fields

Revision ID: d87a839d50d5
Revises: ac86154976c5
Create Date: 2026-07-08 21:41:38.540035

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d87a839d50d5"
down_revision: Union[str, Sequence[str], None] = "ac86154976c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AnimalProfile: 9 new fields (SDD-07)
    op.add_column("animal_profiles", sa.Column("sexo", sa.String(10), nullable=True))
    op.add_column(
        "animal_profiles", sa.Column("fecha_nacimiento", sa.Date(), nullable=True)
    )
    op.add_column(
        "animal_profiles", sa.Column("etapa_madurez", sa.String(20), nullable=True)
    )
    op.add_column(
        "animal_profiles",
        sa.Column(
            "condiciones_especiales", postgresql.ARRAY(sa.String()), nullable=True
        ),
    )
    op.add_column(
        "animal_profiles",
        sa.Column(
            "compatible_ninos",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "animal_profiles",
        sa.Column(
            "compatible_otros_animales",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "animal_profiles", sa.Column("microchip", sa.String(50), nullable=True)
    )
    op.add_column(
        "animal_profiles",
        sa.Column(
            "data_origin",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'source_submitted'"),
        ),
    )
    op.add_column("animal_profiles", sa.Column("source_url", sa.Text(), nullable=True))

    # Campaign: 2 new fields (SDD-07)
    op.add_column(
        "campaigns",
        sa.Column(
            "data_origin",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'source_submitted'"),
        ),
    )
    op.add_column("campaigns", sa.Column("source_url", sa.Text(), nullable=True))

    # FixedPoint: 2 new fields (SDD-07)
    op.add_column(
        "fixed_points",
        sa.Column(
            "data_origin",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'source_submitted'"),
        ),
    )
    op.add_column("fixed_points", sa.Column("source_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("animal_profiles", "source_url")
    op.drop_column("animal_profiles", "data_origin")
    op.drop_column("animal_profiles", "microchip")
    op.drop_column("animal_profiles", "compatible_otros_animales")
    op.drop_column("animal_profiles", "compatible_ninos")
    op.drop_column("animal_profiles", "condiciones_especiales")
    op.drop_column("animal_profiles", "etapa_madurez")
    op.drop_column("animal_profiles", "fecha_nacimiento")
    op.drop_column("animal_profiles", "sexo")

    op.drop_column("campaigns", "source_url")
    op.drop_column("campaigns", "data_origin")

    op.drop_column("fixed_points", "source_url")
    op.drop_column("fixed_points", "data_origin")
