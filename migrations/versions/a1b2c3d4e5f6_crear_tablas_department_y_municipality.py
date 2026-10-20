"""crear tablas department y municipality para datos geográficos de Colombia

Revision ID: a1b2c3d4e5f6
Revises: a8cf202515a5
Create Date: 2026-07-08

Datos cargados desde seed estático (data/colombia/), no desde API en runtime.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "a8cf202515a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_departments_name"), "departments", ["name"])

    op.create_table(
        "municipalities",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_municipalities_name"), "municipalities", ["name"])
    op.create_index(
        op.f("ix_municipalities_department_id"),
        "municipalities",
        ["department_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_municipalities_department_id"), table_name="municipalities")
    op.drop_index(op.f("ix_municipalities_name"), table_name="municipalities")
    op.drop_table("municipalities")
    op.drop_index(op.f("ix_departments_name"), table_name="departments")
    op.drop_table("departments")
