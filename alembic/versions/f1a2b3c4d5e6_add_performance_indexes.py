"""add_performance_indexes

Revision ID: f1a2b3c4d5e6
Revises: b3c5d7e9f012
Create Date: 2026-03-26

Qué hace esta migración:
- Agrega índices en columnas usadas como filtros frecuentes en los CRUDs.
- Las columnas con unique=True (email, name, contact_email) ya tienen índice
  implícito creado por PostgreSQL — no se duplican aquí.
- Índices booleanos (is_active): útiles cuando la mayoría de registros son
  activos y se filtra por inactivos (subconjunto pequeño).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "b3c5d7e9f012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users ---
    # is_active: filtro en get_users() — separa activos de inactivos
    # role: filtro en get_users() — separa Administradores de Empleados
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_users_role", "users", ["role"])

    # --- products ---
    # is_active: filtro en get_products() — catálogo activo vs desactivado
    # category: filtro en get_products() — listar por categoría
    op.create_index("ix_products_is_active", "products", ["is_active"])
    op.create_index("ix_products_category", "products", ["category"])

    # --- suppliers ---
    # is_active: filtro en get_suppliers() — proveedores activos vs desactivados
    op.create_index("ix_suppliers_is_active", "suppliers", ["is_active"])

    # --- orders ---
    # supplier_id: filtro en get_orders() — pedidos de un proveedor específico
    # status: filtro en get_orders() — PENDIENTE | COMPLETADO | CANCELADO
    op.create_index("ix_orders_supplier_id", "orders", ["supplier_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # --- inventory_movements ---
    # product_id: filtro en get_movements() — historial de un producto
    # movement_type: filtro en get_movements() — ENTRADA | SALIDA
    op.create_index("ix_inventory_movements_product_id", "inventory_movements", ["product_id"])
    op.create_index("ix_inventory_movements_movement_type", "inventory_movements", ["movement_type"])


def downgrade() -> None:
    # Revertir en orden inverso al upgrade
    op.drop_index("ix_inventory_movements_movement_type", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_product_id", table_name="inventory_movements")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_supplier_id", table_name="orders")
    op.drop_index("ix_suppliers_is_active", table_name="suppliers")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_is_active", table_name="products")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
