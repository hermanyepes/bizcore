# ============================================================
# BizCore — Tests de RBAC: matriz de permisos por rol
# ============================================================
#
# Este archivo verifica la matriz de permisos definida en
# docs/roles/matriz-permisos.md para todos los módulos.
#
# Cubre las celdas nuevas del modelo de 4 roles:
#   - Superadmin, Administrador, Supervisor, Empleado
#
# Para cada celda importante de la matriz hay al menos un test:
#   ✅ Permitido → verifica que el endpoint devuelve 200/201
#   ❌ Denegado  → verifica que el endpoint devuelve 403
#
# Los fixtures vienen de tests/conftest.py:
#   - admin_token, admin_user           → Administrador
#   - employee_token, employee_user     → Empleado
#   - superadmin_token, superadmin_user → Superadmin (nuevo)
#   - supervisor_token, supervisor_user → Supervisor (nuevo)
#   - product, supplier                 → datos de prueba
#
# ============================================================

import httpx

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User

# ============================================================
# Módulo: Usuarios — Listar y leer
# ============================================================


async def test_admin_can_list_users(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """GET /users con token de Admin devuelve 200."""
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


async def test_supervisor_cannot_list_users(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
):
    """GET /users con token de Supervisor devuelve 403."""
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 403


async def test_employee_cannot_list_users(
    client: httpx.AsyncClient,
    employee_token: str,
    employee_user: User,
):
    """GET /users con token de Empleado devuelve 403."""
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


# ============================================================
# Módulo: Usuarios — Crear con distintos roles (HU-018)
# ============================================================


async def test_admin_can_create_employee_user(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """Admin puede crear un usuario con rol Empleado → 201."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "document_id": "5000000005",
            "document_type": "CC",
            "full_name": "Empleado Nuevo",
            "email": "nuevo.empleado@test.com",
            "role": "Empleado",
            "password": "Segura@2026",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "Empleado"


async def test_admin_can_create_supervisor_user(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """Admin puede crear un usuario con rol Supervisor → 201."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "document_id": "6000000006",
            "document_type": "CC",
            "full_name": "Supervisor Nuevo",
            "email": "nuevo.supervisor@test.com",
            "role": "Supervisor",
            "password": "Segura@2026",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "Supervisor"


async def test_admin_cannot_create_admin_user(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """HU-018: Admin intenta crear rol Administrador → 403."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "document_id": "7000000007",
            "document_type": "CC",
            "full_name": "Admin Nuevo",
            "email": "nuevo.admin@test.com",
            "role": "Administrador",
            "password": "Segura@2026",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403


async def test_admin_cannot_create_superadmin_user(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """HU-018: Admin intenta crear rol Superadmin → 403."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "document_id": "8000000008",
            "document_type": "CC",
            "full_name": "Superadmin Nuevo",
            "email": "nuevo.superadmin@test.com",
            "role": "Superadmin",
            "password": "Segura@2026",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403


async def test_superadmin_can_create_admin_user(
    client: httpx.AsyncClient,
    superadmin_token: str,
    superadmin_user: User,
    admin_user: User,
):
    """HU-018: Superadmin puede crear rol Administrador → 201."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "document_id": "4000000004",
            "document_type": "CC",
            "full_name": "Admin Creado por Super",
            "email": "admin.por.super@test.com",
            "role": "Administrador",
            "password": "Segura@2026",
        },
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "Administrador"


async def test_supervisor_cannot_create_any_user(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
):
    """Supervisor no puede crear usuarios — no tiene acceso al módulo → 403."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "document_id": "2500000025",
            "document_type": "CC",
            "full_name": "Usuario Prohibido",
            "email": "prohibido@test.com",
            "role": "Empleado",
            "password": "Segura@2026",
        },
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 403


# ============================================================
# Módulo: Usuarios — Actualizar y eliminar (HU-018)
# ============================================================


async def test_admin_cannot_update_superadmin_user(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
    superadmin_user: User,
):
    """HU-018: Admin no puede modificar a un Superadmin → 403."""
    response = await client.put(
        f"/api/v1/users/{superadmin_user.document_id}",
        json={"full_name": "Nombre Hackeado"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403


async def test_admin_cannot_promote_to_admin_role(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
    employee_user: User,
):
    """HU-018: Admin no puede promover un Empleado a Administrador → 403."""
    response = await client.put(
        f"/api/v1/users/{employee_user.document_id}",
        json={"role": "Administrador"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403


async def test_admin_cannot_delete_superadmin_user(
    client: httpx.AsyncClient,
    admin_token: str,
    admin_user: User,
    superadmin_user: User,
):
    """HU-018: Admin no puede desactivar a un Superadmin → 403."""
    response = await client.delete(
        f"/api/v1/users/{superadmin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403


# ============================================================
# Módulo: Productos — Crear, actualizar, eliminar
# ============================================================


async def test_supervisor_can_create_product(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
):
    """Supervisor puede crear productos → 201."""
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Producto del Supervisor", "price": 5000},
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 201


async def test_employee_cannot_create_product(
    client: httpx.AsyncClient,
    employee_token: str,
    employee_user: User,
):
    """Empleado no puede crear productos → 403."""
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Producto Prohibido", "price": 5000},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_supervisor_cannot_delete_product(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
    product: Product,
):
    """Supervisor no puede hacer soft delete de productos (solo Admin+) → 403."""
    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 403


# ============================================================
# Módulo: Proveedores — Listar, crear, eliminar
# ============================================================


async def test_employee_cannot_list_suppliers(
    client: httpx.AsyncClient,
    employee_token: str,
    employee_user: User,
):
    """Empleado no puede listar proveedores → 403."""
    response = await client.get(
        "/api/v1/suppliers/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_supervisor_can_create_supplier(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
):
    """Supervisor puede crear proveedores → 201."""
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": "Proveedor del Supervisor"},
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 201


async def test_supervisor_cannot_delete_supplier(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
    supplier: Supplier,
):
    """Supervisor no puede hacer soft delete de proveedores (solo Admin+) → 403."""
    response = await client.delete(
        f"/api/v1/suppliers/{supplier.id}",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 403


# ============================================================
# Módulo: Inventario — Listar y registrar movimientos
# ============================================================


async def test_employee_cannot_list_inventory(
    client: httpx.AsyncClient,
    employee_token: str,
    employee_user: User,
):
    """Empleado no puede listar movimientos de inventario → 403."""
    response = await client.get(
        "/api/v1/inventory/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_supervisor_can_register_entrada(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
    product: Product,
):
    """Supervisor puede registrar una ENTRADA de inventario → 201."""
    response = await client.post(
        "/api/v1/inventory/",
        json={
            "product_id": product.id,
            "movement_type": "ENTRADA",
            "quantity": 10,
        },
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 201


async def test_supervisor_cannot_register_ajuste(
    client: httpx.AsyncClient,
    supervisor_token: str,
    supervisor_user: User,
    product: Product,
):
    """
    Supervisor no puede registrar un AJUSTE de inventario → 403.

    AJUSTE es una corrección contable que requiere Admin+.
    El endpoint verifica el tipo de movimiento después de pasar require_supervisor.
    """
    response = await client.post(
        "/api/v1/inventory/",
        json={
            "product_id": product.id,
            "movement_type": "AJUSTE",
            "quantity": 42,
            "notes": "Intento de ajuste por Supervisor",
        },
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert response.status_code == 403
