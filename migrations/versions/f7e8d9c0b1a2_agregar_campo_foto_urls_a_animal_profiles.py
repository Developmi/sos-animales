"""agregar campo foto_urls a animal_profiles para múltiples fotos

Revision ID: f7e8d9c0b1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-08

Permite almacenar hasta 4 fotos adicionales por animal.
foto_url sigue siendo la principal (obligatoria).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f7e8d9c0b1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente: solo agrega la columna si no existe.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS ("
        "  SELECT 1 FROM information_schema.columns "
        "  WHERE table_name='animal_profiles' AND column_name='foto_urls'"
        ") THEN "
        "  ALTER TABLE animal_profiles ADD COLUMN foto_urls VARCHAR(500)[]; "
        "END IF; "
        "END $$;"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS ("
        "  SELECT 1 FROM information_schema.columns "
        "  WHERE table_name='animal_profiles' AND column_name='foto_urls'"
        ") THEN "
        "  ALTER TABLE animal_profiles DROP COLUMN foto_urls; "
        "END IF; "
        "END $$;"
    )
