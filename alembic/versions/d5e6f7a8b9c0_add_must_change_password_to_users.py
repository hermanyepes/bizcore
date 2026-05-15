"""add_must_change_password_to_users

Revision ID: d5e6f7a8b9c0
Revises: c8d9e0f1a2b3
Create Date: 2026-05-15

Qué hace esta migración:
- Agrega columna `must_change_password` (BOOLEAN NOT NULL DEFAULT FALSE)
  a la tabla `users`.

¿Por qué DEFAULT FALSE para filas existentes?
Los usuarios ya creados tienen contraseñas conocidas — no es necesario
forzarles un cambio. Solo el admin creado por seed (contraseña generada
automáticamente) arranca con TRUE.

¿Cuándo se pone en TRUE?
Solo en scripts/seed_admin.py, que genera la contraseña aleatoriamente
y no puede mostrarla más de una vez. La lógica que fuerza el cambio
en el endpoint /login se implementa en la Sesión 8 del roadmap.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agregar columna must_change_password a users."""
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Revertir: eliminar columna must_change_password de users."""
    op.drop_column("users", "must_change_password")
