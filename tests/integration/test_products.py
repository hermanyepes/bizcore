# ============================================================
# BizCore — Tests de integración: /api/v1/products (CRUD completo)
# ============================================================
#
# Probamos los 5 endpoints de productos:
#
#   GET    /api/v1/products/          → listar (paginado)
#   GET    /api/v1/products/{id}      → obtener uno
#   POST   /api/v1/products/          → crear (solo Administrador)
#   PUT    /api/v1/products/{id}      → actualizar (solo Administrador)
#   DELETE /api/v1/products/{id}      → desactivar (solo Administrador)
#
# Para cada endpoint probamos:
#   ✓ Happy path (funciona bien)
#   ✗ Sin autenticación (→ 401)
#   ✗ Rol insuficiente (→ 403)
#   ✗ Recurso no encontrado (→ 404)
#   ✗ Conflicto de datos (→ 409)
#
# DIFERENCIA con test_users.py:
#   - Los empleados pueden LEER productos (GET), pero no modificarlos
#   - El id del producto es un entero autoincremental (no un documento)
#   - Soft delete devuelve el producto con is_active=False
#
# Los fixtures vienen de tests/conftest.py:
#   - client         → cliente HTTP con BD de prueba
#   - product        → producto ya insertado en la BD
#   - admin_token    → JWT de Administrador
#   - employee_token → JWT de Empleado
#
# ============================================================

from datetime import UTC, datetime

import httpx
import pytest

from app.models.product import Product
from sqlalchemy.ext.asyncio import AsyncSession

# Datos de ejemplo para crear un producto nuevo en los tests de POST
NUEVO_PRODUCTO = {
    "name": "Chorizo Especial",
    "description": "Chorizo artesanal de res",
    "price": 8500,
    "stock": 50,
    "category": "Carnes",
}


# ============================================================
# GET /api/v1/products/ — Listar productos
# ============================================================


async def test_listar_productos_como_admin(
    client: httpx.AsyncClient, admin_token: str, product: Product
):
    """
    GET /products con token de Administrador devuelve 200 y lista paginada.

    Verificamos:
    - Estructura de paginación: items, total, page, page_size, pages
    - El producto del fixture aparece en la respuesta
    """
    response = await client.get(
        "/api/v1/products/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    # Verificar estructura de paginación
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert "pages" in body

    # El producto del fixture debe aparecer en el listado
    assert body["total"] >= 1
    assert any(p["name"] == product.name for p in body["items"])


async def test_listar_productos_como_empleado(
    client: httpx.AsyncClient, employee_token: str, product: Product
):
    """
    GET /products con token de Empleado también devuelve 200.

    ¿Por qué los empleados pueden listar productos?
    Porque necesitan consultar el catálogo para atender a los clientes.
    Solo crear, editar y eliminar requiere ser Administrador.
    """
    response = await client.get(
        "/api/v1/products/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 200


async def test_listar_productos_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /products sin token debe devolver 401."""
    response = await client.get("/api/v1/products/")
    assert response.status_code == 401


# ============================================================
# GET /api/v1/products/{id} — Obtener un producto
# ============================================================


async def test_obtener_producto_por_id(
    client: httpx.AsyncClient, admin_token: str, product: Product
):
    """
    GET /products/{id} con un id que existe devuelve 200 y los datos del producto.

    Verificamos todos los campos que ProductResponse debe devolver.
    """
    response = await client.get(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"] == product.id
    assert body["name"] == product.name
    assert body["price"] == product.price
    assert body["stock"] == product.stock
    assert body["is_active"] is True
    assert "created_at" in body


async def test_obtener_producto_como_empleado(
    client: httpx.AsyncClient, employee_token: str, product: Product
):
    """Un empleado también puede ver los detalles de un producto específico."""
    response = await client.get(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 200


async def test_obtener_producto_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """GET /products/{id} con un id que no existe devuelve 404."""
    response = await client.get(
        "/api/v1/products/9999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_obtener_producto_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /products/{id} sin token devuelve 401."""
    response = await client.get("/api/v1/products/1")
    assert response.status_code == 401


# ============================================================
# POST /api/v1/products/ — Crear producto
# ============================================================


async def test_crear_producto_como_admin(
    client: httpx.AsyncClient, admin_token: str
):
    """
    POST /products con token de Administrador devuelve 201 y el producto creado.

    Verificamos:
    - Status 201 Created (no 200)
    - Los campos enviados en el body están en la respuesta
    - `id` y `created_at` fueron generados por la BD (no los enviamos)
    - `is_active` arranca en True por defecto
    """
    response = await client.post(
        "/api/v1/products/",
        json=NUEVO_PRODUCTO,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201

    body = response.json()
    assert body["name"] == NUEVO_PRODUCTO["name"]
    assert body["price"] == NUEVO_PRODUCTO["price"]
    assert body["stock"] == NUEVO_PRODUCTO["stock"]
    assert body["is_active"] is True
    # id y created_at los genera la BD — solo verificamos que existen
    assert "id" in body
    assert "created_at" in body


async def test_crear_producto_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str
):
    """
    POST /products con token de Empleado devuelve 403 Forbidden.

    ¿Por qué 403 y no 401?
    401 = no hay token (o el token es inválido) → "¿quién eres?"
    403 = el token es válido pero el rol no tiene permiso → "sé quién eres, pero no puedes"
    """
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Producto Prohibido", "price": 1000},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_crear_producto_sin_token_devuelve_401(client: httpx.AsyncClient):
    """POST /products sin token devuelve 401."""
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Producto Sin Auth", "price": 1000},
    )
    assert response.status_code == 401


async def test_crear_producto_nombre_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, product: Product
):
    """
    POST /products con un nombre que ya existe devuelve 409 Conflict.

    `product` ya está en la BD con name="Café Especial".
    Intentamos crear otro con el mismo nombre → el endpoint lo detecta
    con get_product_by_name() y lanza HTTP 409 antes de hacer el INSERT.
    """
    response = await client.post(
        "/api/v1/products/",
        json={"name": product.name, "price": 5000},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 409


async def test_crear_producto_datos_invalidos_devuelve_422(
    client: httpx.AsyncClient, admin_token: str
):
    """
    POST /products con price=0 devuelve 422 — Pydantic rechaza antes del endpoint.

    ProductCreate tiene `price: int = Field(gt=0)`.
    gt=0 significa "greater than 0": el precio debe ser estrictamente mayor a cero.
    Pydantic intercepta price=0 antes de que la request llegue al endpoint.
    """
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Precio Cero", "price": 0},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


# ============================================================
# PUT /api/v1/products/{id} — Actualizar producto
# ============================================================


async def test_actualizar_producto_como_admin(
    client: httpx.AsyncClient, admin_token: str, product: Product
):
    """
    PUT /products/{id} con token de Administrador devuelve 200 con datos actualizados.

    Enviamos solo price y stock (exclude_unset=True en el CRUD garantiza
    que el name y los otros campos no se sobreescriban con None).
    """
    response = await client.put(
        f"/api/v1/products/{product.id}",
        json={"price": 20000, "stock": 200},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["price"] == 20000
    assert body["stock"] == 200
    assert body["name"] == product.name  # el nombre no se tocó


async def test_actualizar_producto_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str, product: Product
):
    """PUT /products/{id} con token de Empleado devuelve 403."""
    response = await client.put(
        f"/api/v1/products/{product.id}",
        json={"price": 99999},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_actualizar_producto_sin_token_devuelve_401(
    client: httpx.AsyncClient, product: Product
):
    """PUT /products/{id} sin token devuelve 401."""
    response = await client.put(
        f"/api/v1/products/{product.id}",
        json={"price": 99999},
    )
    assert response.status_code == 401


async def test_actualizar_producto_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """PUT /products/{id} con un id que no existe devuelve 404."""
    response = await client.put(
        "/api/v1/products/9999",
        json={"price": 5000},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_actualizar_nombre_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, product: Product, db: AsyncSession
):
    """
    Renombrar un producto con el nombre de otro devuelve 409.

    Para este test necesitamos DOS productos:
    - `product` ya existe con name="Café Especial" (viene del fixture)
    - `second` lo creamos aquí directamente en la BD
    - Intentamos renombrar `second` con el nombre de `product` → 409

    ¿Por qué creamos `second` directo en la BD y no con POST?
    Para no hacer que este test dependa del endpoint POST.
    Si POST tuviera un bug, este test fallaría por la razón equivocada.
    """
    # Arrange: crear un segundo producto directamente en la BD de prueba
    second = Product(
        name="Segundo Producto",
        price=3000,
        stock=10,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(second)
    await db.commit()
    await db.refresh(second)

    # Act: intentar renombrar `second` con el nombre que ya usa `product`
    response = await client.put(
        f"/api/v1/products/{second.id}",
        json={"name": product.name},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Assert: el endpoint detecta el conflicto y responde 409
    assert response.status_code == 409


# ============================================================
# DELETE /api/v1/products/{id} — Desactivar producto (soft delete)
# ============================================================


async def test_desactivar_producto_como_admin(
    client: httpx.AsyncClient, admin_token: str, product: Product
):
    """
    DELETE /products/{id} con token de Administrador devuelve 200.

    El producto NO se borra de la BD: is_active pasa de True a False.
    La respuesta devuelve el producto con is_active=False como confirmación.

    ¿Por qué 200 y no 204?
    204 No Content = éxito sin cuerpo de respuesta.
    Nosotros devolvemos el producto actualizado (is_active=False),
    así el cliente confirma visualmente que el soft delete se hizo bien.
    """
    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"] == product.id
    assert body["is_active"] is False  # confirmación del soft delete


async def test_desactivar_producto_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str, product: Product
):
    """DELETE /products/{id} con token de Empleado devuelve 403."""
    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_desactivar_producto_sin_token_devuelve_401(
    client: httpx.AsyncClient, product: Product
):
    """DELETE /products/{id} sin token devuelve 401."""
    response = await client.delete(f"/api/v1/products/{product.id}")
    assert response.status_code == 401


async def test_desactivar_producto_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """DELETE /products/{id} con un id que no existe devuelve 404."""
    response = await client.delete(
        "/api/v1/products/9999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404
