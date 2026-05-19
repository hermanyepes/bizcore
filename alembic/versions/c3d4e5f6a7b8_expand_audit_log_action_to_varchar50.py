"""expand_audit_log_action_to_varchar50

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-19

Qué hace esta migración:
- Amplía la columna `action` de `audit_logs` de VARCHAR(10) a VARCHAR(50).

Por qué era necesario:
  El valor original VARCHAR(10) solo soportaba "create", "update", "delete".
  El nuevo valor "force_logout" tiene 12 caracteres y reventaba con
  StringDataRightTruncationError al intentar insertar el log de HU-009.

Por qué VARCHAR(50) y no VARCHAR(10):
  Da margen para futuros valores compuestos (ej. "password_change",
  "bulk_deactivate") sin necesidad de otra migración.
"""

from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'  # pragma: allowlist secret
down_revision = 'b2c3d4e5f6a7'  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'audit_logs',
        'action',
        existing_type=sa.String(10),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    # ADVERTENCIA: si hay filas con action > 10 chars, el downgrade fallará.
    op.alter_column(
        'audit_logs',
        'action',
        existing_type=sa.String(50),
        type_=sa.String(10),
        existing_nullable=False,
    )
