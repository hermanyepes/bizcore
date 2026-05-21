"""add_rbac_columns_cost_price_margin_cancel_reason

Revision ID: a1b2c3d4e5f7
Revises: e7f8a9b0c1d2
Create Date: 2026-05-18

Qué hace esta migración:
- Agrega cost_price INTEGER NULL y margin INTEGER NULL a `products`.
  Necesarios para column-level security (HU-022): el Empleado ve solo
  el precio de venta; el Supervisor+ también ve costo y margen.
- Agrega cancel_reason TEXT NULL a `orders`.
  Requerido por row-level security (HU-046): el Empleado debe proveer
  una razón al cancelar su propia orden pendiente.

¿Por qué nullable?
- cost_price / margin: productos legacy ya existentes no tienen costo
  registrado. Los nuevos pueden setearlo en el POST/PUT.
- cancel_reason: solo se llena cuando el status pasa a CANCELADA.
  Las órdenes en otros estados la tienen en NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f7"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # asyncpg no acepta múltiples sentencias en un execute — una llamada por ALTER
    op.add_column("products", sa.Column("cost_price", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("margin", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("cancel_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "cancel_reason")
    op.drop_column("products", "margin")
    op.drop_column("products", "cost_price")
