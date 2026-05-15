"""add_supervisor_and_superadmin_roles_with_check_constraint

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-05-15

Qué hace esta migración:
- Elimina el CHECK constraint actual de `role` en `users` (si existe).
- Agrega un nuevo CHECK constraint con los 4 roles del modelo objetivo:
  Superadmin, Administrador, Supervisor, Empleado.

¿Por qué DROP + ADD en vez de ALTER CONSTRAINT?
PostgreSQL no soporta ALTER CONSTRAINT para constraints de tipo CHECK.
El único camino es eliminar el existente y crear uno nuevo.

¿Qué pasa con los datos existentes?
Los usuarios actuales con role='Administrador' o role='Empleado' son
compatibles con el nuevo constraint — no se necesita UPDATE de datos.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ampliar el CHECK constraint de role a los 4 roles del modelo objetivo."""
    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('Superadmin', 'Administrador', 'Supervisor', 'Empleado'));
    """)


def downgrade() -> None:
    """Revertir: volver al CHECK constraint con solo los 2 roles originales."""
    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('Administrador', 'Empleado'));
    """)
