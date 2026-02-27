"""rename_usuario_to_users_english_columns

Revision ID: 2c70ca836291
Revises: ea3e45d32e8d
Create Date: 2026-02-26

Qué hace esta migración:
- Renombra la tabla `usuario` → `users`
- Renombra todas las columnas en español a inglés

¿Por qué una migración nueva y no editar la anterior?
La migración ea3e45d32e8d ya fue aplicada a la BD real.
Editarla rompería el historial de Alembic: la BD y el
historial quedarían desincronizados. Siempre se crea una
migración nueva para cambios posteriores.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c70ca836291"
down_revision: str | Sequence[str] | None = "ea3e45d32e8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Renombrar tabla y columnas de español a inglés."""

    # 1. Renombrar columnas ANTES de renombrar la tabla
    #    (op.alter_column trabaja sobre el nombre actual de la tabla)
    op.alter_column("usuario", "id_documento", new_column_name="document_id")
    op.alter_column("usuario", "tipo_documento", new_column_name="document_type")
    op.alter_column("usuario", "nombres", new_column_name="full_name")
    op.alter_column("usuario", "telefono", new_column_name="phone")
    op.alter_column("usuario", "correo", new_column_name="email")
    op.alter_column("usuario", "ciudad", new_column_name="city")
    op.alter_column("usuario", "rol", new_column_name="role")
    op.alter_column("usuario", "fecha_ingreso", new_column_name="join_date")

    # 2. Renombrar la tabla
    op.rename_table("usuario", "users")


def downgrade() -> None:
    """Revertir: volver a español (para rollback si es necesario)."""

    # 1. Renombrar la tabla de vuelta
    op.rename_table("users", "usuario")

    # 2. Revertir los nombres de columna
    op.alter_column("usuario", "document_id", new_column_name="id_documento")
    op.alter_column("usuario", "document_type", new_column_name="tipo_documento")
    op.alter_column("usuario", "full_name", new_column_name="nombres")
    op.alter_column("usuario", "phone", new_column_name="telefono")
    op.alter_column("usuario", "email", new_column_name="correo")
    op.alter_column("usuario", "city", new_column_name="ciudad")
    op.alter_column("usuario", "role", new_column_name="rol")
    op.alter_column("usuario", "join_date", new_column_name="fecha_ingreso")
