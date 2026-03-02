# ============================================================
# BizCore — Tests de integración: /api/v1/suppliers (CRUD completo)
# ============================================================
#
# Probamos los 5 endpoints de proveedores:
#
#   GET    /api/v1/suppliers/        → listar (paginado)
#   GET    /api/v1/suppliers/{id}    → obtener uno
#   POST   /api/v1/suppliers/        → crear (solo Administrador)
#   PUT    /api/v1/suppliers/{id}    → actualizar (solo Administrador)
#   DELETE /api/v1/suppliers/{id}    → desactivar (solo Administrador)
#
# Para cada endpoint probamos:
#   ✓ Happy path (funciona bien)
#   ✗ Sin autenticación (→ 401)
#   ✗ Rol insuficiente (→ 403)
#   ✗ Recurso no encontrado (→ 404)
#   ✗ Conflicto de datos (→ 409) — nombre Y email son únicos
#
# DIFERENCIA con test_products.py:
#   - Hay DOS campos únicos (name y contact_email) → dos pruebas de 409 en POST
#   - El PUT también verifica duplicados de email → dos pruebas de 409 en PUT
#   - EmailStr en el schema permite probar 422 con un email mal formado
#
# Los fixtures vienen de tests/conftest.py:
#   - client         → cliente HTTP con BD de prueba
#   - supplier       → proveedor ya insertado en la BD
#   - admin_token    → JWT de Administrador
#   - employee_token → JWT de Empleado
#
# ============================================================

from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier

# Datos de ejemplo para crear un proveedor nuevo en los tests de POST
NUEVO_PROVEEDOR = {
    "name": "Lácteos del Valle",
    "contact_email": "pedidos@lacteosvalle.com",
    "phone": "602 444 5678",
    "address": "Av. 6N # 23-45, Cali",
}


# ============================================================
# GET /api/v1/suppliers/ — Listar proveedores
# ============================================================


async def test_listar_proveedores_como_admin(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier
):
    """
    GET /suppliers con token de Administrador devuelve 200 y lista paginada.

    Verificamos:
    - Estructura de paginación: items, total, page, page_size, pages
    - El proveedor del fixture aparece en la respuesta
    """
    response = await client.get(
        "/api/v1/suppliers/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert "pages" in body

    assert body["total"] >= 1
    assert any(s["name"] == supplier.name for s in body["items"])


async def test_listar_proveedores_como_empleado(
    client: httpx.AsyncClient, employee_token: str, supplier: Supplier
):
    """
    GET /suppliers con token de Empleado también devuelve 200.

    Los empleados pueden consultar la libreta de proveedores
    para coordinar pedidos. Crear, editar y eliminar sí requiere Admin.
    """
    response = await client.get(
        "/api/v1/suppliers/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 200


async def test_listar_proveedores_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /suppliers sin token devuelve 401."""
    response = await client.get("/api/v1/suppliers/")
    assert response.status_code == 401


# ============================================================
# GET /api/v1/suppliers/{id} — Obtener un proveedor
# ============================================================


async def test_obtener_proveedor_por_id(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier
):
    """
    GET /suppliers/{id} con un id que existe devuelve 200 y los datos del proveedor.

    Verificamos todos los campos que SupplierResponse debe devolver.
    """
    response = await client.get(
        f"/api/v1/suppliers/{supplier.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"] == supplier.id
    assert body["name"] == supplier.name
    assert body["contact_email"] == supplier.contact_email
    assert body["phone"] == supplier.phone
    assert body["is_active"] is True
    assert "created_at" in body


async def test_obtener_proveedor_como_empleado(
    client: httpx.AsyncClient, employee_token: str, supplier: Supplier
):
    """Un empleado también puede ver los detalles de un proveedor específico."""
    response = await client.get(
        f"/api/v1/suppliers/{supplier.id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 200


async def test_obtener_proveedor_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """GET /suppliers/{id} con un id que no existe devuelve 404."""
    response = await client.get(
        "/api/v1/suppliers/9999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_obtener_proveedor_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /suppliers/{id} sin token devuelve 401."""
    response = await client.get("/api/v1/suppliers/1")
    assert response.status_code == 401


# ============================================================
# POST /api/v1/suppliers/ — Crear proveedor
# ============================================================


async def test_crear_proveedor_como_admin(
    client: httpx.AsyncClient, admin_token: str
):
    """
    POST /suppliers con token de Administrador devuelve 201 y el proveedor creado.

    Verificamos:
    - Status 201 Created
    - Los campos enviados aparecen en la respuesta
    - `id` y `created_at` fueron generados por la BD
    - `is_active` arranca en True por defecto
    """
    response = await client.post(
        "/api/v1/suppliers/",
        json=NUEVO_PROVEEDOR,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201

    body = response.json()
    assert body["name"] == NUEVO_PROVEEDOR["name"]
    assert body["contact_email"] == NUEVO_PROVEEDOR["contact_email"]
    assert body["phone"] == NUEVO_PROVEEDOR["phone"]
    assert body["is_active"] is True
    assert "id" in body
    assert "created_at" in body


async def test_crear_proveedor_sin_email(
    client: httpx.AsyncClient, admin_token: str
):
    """
    POST /suppliers sin contact_email devuelve 201.

    contact_email es opcional. Un proveedor puede registrarse
    solo con nombre y sin ningún otro campo.
    """
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": "Proveedor Sin Email"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    assert response.json()["contact_email"] is None


async def test_crear_proveedor_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str
):
    """POST /suppliers con token de Empleado devuelve 403 Forbidden."""
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": "Proveedor Prohibido"},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_crear_proveedor_sin_token_devuelve_401(client: httpx.AsyncClient):
    """POST /suppliers sin token devuelve 401."""
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": "Proveedor Sin Auth"},
    )
    assert response.status_code == 401


async def test_crear_proveedor_nombre_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier
):
    """
    POST /suppliers con un nombre que ya existe devuelve 409.

    `supplier` ya está en la BD con name="Distribuidora El Maíz".
    Intentamos crear otro con el mismo nombre → 409.
    """
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": supplier.name},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 409


async def test_crear_proveedor_email_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier
):
    """
    POST /suppliers con un email que ya existe devuelve 409.

    `supplier` ya tiene contact_email="ventas@maiz.com".
    Intentamos crear otro proveedor (distinto nombre) con el mismo email → 409.
    """
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": "Otro Proveedor", "contact_email": supplier.contact_email},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 409


async def test_crear_proveedor_email_invalido_devuelve_422(
    client: httpx.AsyncClient, admin_token: str
):
    """
    POST /suppliers con un email mal formado devuelve 422.

    SupplierCreate usa EmailStr para contact_email.
    Pydantic rechaza "no-es-un-email" antes de que llegue al endpoint.
    """
    response = await client.post(
        "/api/v1/suppliers/",
        json={"name": "Proveedor Email Malo", "contact_email": "no-es-un-email"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


# ============================================================
# PUT /api/v1/suppliers/{id} — Actualizar proveedor
# ============================================================


async def test_actualizar_proveedor_como_admin(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier
):
    """
    PUT /suppliers/{id} con token de Administrador devuelve 200 con datos actualizados.

    Enviamos solo phone: los demás campos no se tocan gracias a
    exclude_unset=True en el CRUD.
    """
    response = await client.put(
        f"/api/v1/suppliers/{supplier.id}",
        json={"phone": "310 999 0000"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["phone"] == "310 999 0000"
    assert body["name"] == supplier.name  # el nombre no se tocó


async def test_actualizar_proveedor_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str, supplier: Supplier
):
    """PUT /suppliers/{id} con token de Empleado devuelve 403."""
    response = await client.put(
        f"/api/v1/suppliers/{supplier.id}",
        json={"phone": "310 000 0000"},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_actualizar_proveedor_sin_token_devuelve_401(
    client: httpx.AsyncClient, supplier: Supplier
):
    """PUT /suppliers/{id} sin token devuelve 401."""
    response = await client.put(
        f"/api/v1/suppliers/{supplier.id}",
        json={"phone": "310 000 0000"},
    )
    assert response.status_code == 401


async def test_actualizar_proveedor_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """PUT /suppliers/{id} con un id que no existe devuelve 404."""
    response = await client.put(
        "/api/v1/suppliers/9999",
        json={"phone": "310 000 0000"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_actualizar_nombre_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier, db: AsyncSession
):
    """
    Renombrar un proveedor con el nombre de otro devuelve 409.

    Necesitamos DOS proveedores:
    - `supplier` ya existe con name="Distribuidora El Maíz" (viene del fixture)
    - `second` lo creamos aquí directamente en la BD
    - Intentamos renombrar `second` con el nombre de `supplier` → 409
    """
    # Arrange: crear un segundo proveedor directamente en la BD
    second = Supplier(
        name="Segundo Proveedor",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(second)
    await db.commit()
    await db.refresh(second)

    # Act: intentar renombrar `second` con el nombre que ya usa `supplier`
    response = await client.put(
        f"/api/v1/suppliers/{second.id}",
        json={"name": supplier.name},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409


async def test_actualizar_email_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier, db: AsyncSession
):
    """
    Cambiar el email de un proveedor al email de otro devuelve 409.

    Mismo patrón que el test de nombre duplicado:
    necesitamos DOS proveedores para que haya conflicto real.
    """
    # Arrange: crear un segundo proveedor con email distinto
    second = Supplier(
        name="Tercer Proveedor",
        contact_email="otro@proveedor.com",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(second)
    await db.commit()
    await db.refresh(second)

    # Act: intentar cambiar el email de `second` al email que ya usa `supplier`
    response = await client.put(
        f"/api/v1/suppliers/{second.id}",
        json={"contact_email": supplier.contact_email},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409


# ============================================================
# DELETE /api/v1/suppliers/{id} — Desactivar proveedor (soft delete)
# ============================================================


async def test_desactivar_proveedor_como_admin(
    client: httpx.AsyncClient, admin_token: str, supplier: Supplier
):
    """
    DELETE /suppliers/{id} con token de Administrador devuelve 200.

    El proveedor NO se borra de la BD: is_active pasa de True a False.
    La respuesta devuelve el proveedor con is_active=False como confirmación.
    """
    response = await client.delete(
        f"/api/v1/suppliers/{supplier.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"] == supplier.id
    assert body["is_active"] is False  # confirmación del soft delete


async def test_desactivar_proveedor_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str, supplier: Supplier
):
    """DELETE /suppliers/{id} con token de Empleado devuelve 403."""
    response = await client.delete(
        f"/api/v1/suppliers/{supplier.id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_desactivar_proveedor_sin_token_devuelve_401(
    client: httpx.AsyncClient, supplier: Supplier
):
    """DELETE /suppliers/{id} sin token devuelve 401."""
    response = await client.delete(f"/api/v1/suppliers/{supplier.id}")
    assert response.status_code == 401


async def test_desactivar_proveedor_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """DELETE /suppliers/{id} con un id que no existe devuelve 404."""
    response = await client.delete(
        "/api/v1/suppliers/9999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404
