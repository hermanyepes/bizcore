"""add_nit_to_suppliers

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-05-19

Qué hace esta migración:
- Agrega columna `nit` VARCHAR(15) NULL a la tabla `suppliers`.

Por qué es NULL:
  Los proveedores existentes no tienen NIT — hacerlo NOT NULL
  requeriría un default o backfill. NULL mantiene la compatibilidad.

Por qué VARCHAR(15):
  Formato máximo: "XXXXXXXXXXX-D" = 11 dígitos + '-' + 1 DV = 13 chars.
  15 chars da margen para formatos con espacios o puntos.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'  # pragma: allowlist secret
down_revision = 'a1b2c3d4e5f7'  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'suppliers',
        sa.Column('nit', sa.String(15), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('suppliers', 'nit')
