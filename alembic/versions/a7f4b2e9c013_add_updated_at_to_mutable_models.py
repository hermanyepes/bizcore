"""add_updated_at_to_mutable_models

Revision ID: a7f4b2e9c013
Revises: 2c70ca836291
Create Date: 2026-03-03

Qué hace esta migración:
- Agrega columna `updated_at` (TIMESTAMP WITH TIME ZONE, nullable)
  a las tablas: users, products, suppliers

¿Por qué nullable y sin server_default?
La columna debe empezar en NULL para los registros existentes.
No queremos retroactivamente "fingir" que todos fueron actualizados
en la fecha de la migración — eso sería información falsa.

El valor se llenará automáticamente en el siguiente UPDATE
sobre cada fila, via el `onupdate=func.now()` en el modelo
SQLAlchemy (no es un trigger de BD — SQLAlchemy lo incluye
en el UPDATE statement al momento de ejecutarlo).

¿Por qué esta migración y no editar las anteriores?
Las migraciones 2c70ca836291 y ea3e45d32e8d ya fueron aplicadas
a la BD real. Editarlas rompería el historial de Alembic.
Siempre se crea una migración nueva para cambios posteriores.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f4b2e9c013"
down_revision: str | Sequence[str] | None = "2c70ca836291"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agregar columna updated_at a users, products y suppliers."""

    # users — tabla de usuarios
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,  # NULL para registros existentes
        ),
    )

    # products — tabla de productos
    op.add_column(
        "products",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # suppliers — tabla de proveedores
    op.add_column(
        "suppliers",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Revertir: eliminar columna updated_at de las tres tablas."""

    # El orden de downgrade es el inverso del upgrade
    op.drop_column("suppliers", "updated_at")
    op.drop_column("products", "updated_at")
    op.drop_column("users", "updated_at")
