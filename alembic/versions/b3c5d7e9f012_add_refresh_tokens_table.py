"""add_refresh_tokens_table

Revision ID: b3c5d7e9f012
Revises: a7f4b2e9c013
Create Date: 2026-03-03

Qué hace esta migración:
- Crea la tabla `refresh_tokens` para el sistema de refresh token rotation.

Columnas:
- id           UUID (PK) — globalmente único, no revela conteo de sesiones
- user_id      VARCHAR(20) — FK a users.document_id con CASCADE DELETE
- token_hash   VARCHAR(64) — SHA256 del token raw (64 hex chars)
- expires_at   TIMESTAMP WITH TIME ZONE — cuándo vence la sesión
- is_revoked   BOOLEAN — True si fue revocado por logout o rotación
- created_at   TIMESTAMP WITH TIME ZONE — cuándo se creó la sesión

Índices creados:
- PK en id
- UNIQUE + INDEX en token_hash (búsqueda por hash en cada /refresh)

¿Por qué guardar el hash y no el token raw?
Si la BD es comprometida, el atacante solo obtiene SHA256 de los tokens.
SHA256 no es reversible: no puede recuperar los tokens originales.

¿Por qué no borrar los tokens revocados inmediatamente?
Auditoría: registro de sesiones cerradas.
Detección de reuso: si un token ya revocado aparece de nuevo,
es señal de que alguien lo está intentando reutilizar.
Una tarea de limpieza periódica puede borrar registros viejos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c5d7e9f012"
down_revision: str | Sequence[str] | None = "a7f4b2e9c013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crear la tabla refresh_tokens."""

    op.create_table(
        "refresh_tokens",
        # PK — UUID como string de 36 chars (formato: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
        sa.Column("id", sa.String(36), nullable=False),
        # FK al usuario dueño de esta sesión
        sa.Column("user_id", sa.String(20), nullable=False),
        # SHA256(raw_token) — 64 caracteres hexadecimales
        sa.Column("token_hash", sa.String(64), nullable=False),
        # Cuándo expira esta sesión
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # False = activo, True = revocado (logout o rotación)
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        # Auditoría: cuándo se creó
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Restricciones
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.document_id"],
            ondelete="CASCADE",  # si el usuario se borra, sus tokens también
        ),
    )

    # Índice en token_hash para búsquedas rápidas en /refresh y /logout.
    # Sin este índice, cada petición sería un full table scan.
    # Con el índice, PostgreSQL usa un B-tree y la búsqueda es O(log n).
    op.create_index(
        op.f("ix_refresh_tokens_token_hash"),
        "refresh_tokens",
        ["token_hash"],
        unique=False,  # ya hay UNIQUE constraint arriba; este es solo para el índice
    )


def downgrade() -> None:
    """Revertir: eliminar la tabla refresh_tokens."""

    # Primero el índice, luego la tabla (PostgreSQL lo requiere)
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
