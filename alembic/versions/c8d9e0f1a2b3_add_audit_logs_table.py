"""add_audit_logs_table

Revision ID: c8d9e0f1a2b3
Revises: f1a2b3c4d5e6
Create Date: 2026-03-26

Qué hace esta migración:
- Crea la tabla `audit_logs` para registrar quién hizo qué
  acción sobre qué recurso y cuándo.

Columnas:
- id          INTEGER (PK autoincremental)
- user_id     VARCHAR(20) — FK a users.document_id
- action      VARCHAR(10) — "create" | "update" | "delete"
- resource    VARCHAR(30) — módulo afectado ("product", "order", ...)
- resource_id VARCHAR(50) — ID del objeto afectado como texto
- changes     JSON        — antes/después en "update", NULL en otros
- timestamp   TIMESTAMP   — asignado por PostgreSQL automáticamente

Índices creados:
- ix_audit_logs_user_id    — consultas por usuario ("¿qué hizo Juan?")
- ix_audit_logs_resource   — consultas por módulo ("¿qué pasó en órdenes?")
- ix_audit_logs_timestamp  — consultas por rango de fecha

¿Por qué no hay ondelete CASCADE en la FK de user_id?
Si un usuario es desactivado (soft delete), sus logs deben conservarse.
Son evidencia — no deben borrarse aunque el usuario ya no esté activo.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crear la tabla audit_logs con sus índices."""

    op.create_table(
        "audit_logs",
        # PK autoincremental — PostgreSQL asigna el número solo
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        # FK al usuario que ejecutó la acción — String porque la PK
        # de users es VARCHAR (número de documento), no un entero
        sa.Column("user_id", sa.String(20), nullable=False),
        # Qué tipo de acción: "create", "update" o "delete"
        sa.Column("action", sa.String(10), nullable=False),
        # Módulo afectado: "user", "product", "order", etc.
        sa.Column("resource", sa.String(30), nullable=False),
        # ID del objeto afectado — siempre como texto para unificar
        # módulos con distintos tipos de PK (int vs varchar)
        sa.Column("resource_id", sa.String(50), nullable=False),
        # JSON con estado antes/después — solo aplica a "update"
        # NULL en "create" y "delete"
        sa.Column("changes", sa.JSON(), nullable=True),
        # Timestamp generado por PostgreSQL al insertar la fila
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.document_id"],
            # Sin ondelete CASCADE: los logs se conservan aunque
            # el usuario sea desactivado — son evidencia permanente
        ),
    )

    # Índice en user_id — para consultas "¿qué hizo este usuario?"
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    # Índice en resource — para consultas "¿qué pasó en este módulo?"
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource"])

    # Índice en timestamp — para filtrar por rango de fechas
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    """Revertir: eliminar índices y luego la tabla."""

    # Primero los índices, luego la tabla
    # (PostgreSQL requiere este orden — no puede borrar una tabla
    # que tiene índices sin borrarlos antes)
    op.drop_index("ix_audit_logs_timestamp", table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
