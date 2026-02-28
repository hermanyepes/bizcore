# ============================================================
# BizCore — Tests de integración: /api/v1/inventory
# ============================================================
#
# Probamos los 3 endpoints de inventario:
#
#   GET  /api/v1/inventory/          → listar movimientos (paginado)
#   GET  /api/v1/inventory/{id}      → obtener uno
#   POST /api/v1/inventory/          → registrar movimiento
#
# Para cada endpoint probamos:
#   ✓ Happy path (funciona bien)
#   ✗ Sin autenticación (→ 401)
#   ✗ Recurso no encontrado (→ 404)
#   ✗ Reglas de negocio violadas (→ 400)
#   ✗ Datos inválidos (→ 422)
#
# DIFERENCIA CLAVE respecto a test_products.py:
#   - No hay tests de 403: tanto Admin como Empleado pueden
#     registrar y consultar movimientos.
#   - El POST más importante verifica el efecto secundario:
#     que product.stock se actualiza correctamente.
#   - Hay 3 tipos de movimiento con lógica distinta: ENTRADA,
#     SALIDA y AJUSTE — cada uno tiene su propio happy path.
#
# Los fixtures vienen de tests/conftest.py:
#   - client             → cliente HTTP con BD de prueba
#   - product            → producto con stock=100 ya en la BD
#   - admin_user         → usuario Administrador
#   - admin_token        → JWT de Administrador
#   - employee_token     → JWT de Empleado
#   - inventory_movement → movimiento ENTRADA ya en la BD
#
# ============================================================

from datetime import UTC, datetime

import httpx
import pytest

from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================
# GET /api/v1/inventory/ — Listar movimientos
# ============================================================


async def test_listar_movimientos_como_admin(
    client: httpx.AsyncClient,
    admin_token: str,
    inventory_movement: InventoryMovement,
):
    """
    GET /inventory/ con token de Admin devuelve 200 y estructura paginada.

    Verificamos:
    - Estructura de paginación: items, total, page, page_size, pages
    - El movimiento del fixture aparece en la respuesta
    """
    response = await client.get(
        "/api/v1/inventory/",
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


async def test_listar_movimientos_como_empleado(
    client: httpx.AsyncClient,
    employee_token: str,
    inventory_movement: InventoryMovement,
):
    """
    GET /inventory/ con token de Empleado también devuelve 200.

    Los empleados también consultan el historial de inventario.
    No hay restricción de rol para lectura.
    """
    response = await client.get(
        "/api/v1/inventory/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 200


async def test_listar_movimientos_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /inventory/ sin token devuelve 401."""
    response = await client.get("/api/v1/inventory/")
    assert response.status_code == 401


async def test_listar_movimientos_filtrado_por_producto(
    client: httpx.AsyncClient,
    admin_token: str,
    inventory_movement: InventoryMovement,
    product: Product,
):
    """
    GET /inventory/?product_id=X devuelve solo los movimientos de ese producto.

    Verificamos que el filtro funciona: todos los items en la respuesta
    deben tener el product_id que pedimos.
    """
    response = await client.get(
        f"/api/v1/inventory/?product_id={product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["total"] >= 1
    # Todos los movimientos en la página deben ser de este producto
    for item in body["items"]:
        assert item["product_id"] == product.id


# ============================================================
# GET /api/v1/inventory/{id} — Obtener un movimiento
# ============================================================


async def test_obtener_movimiento_por_id(
    client: httpx.AsyncClient,
    admin_token: str,
    inventory_movement: InventoryMovement,
):
    """
    GET /inventory/{id} con un id que existe devuelve 200 y los datos correctos.

    Verificamos todos los campos que InventoryMovementResponse debe devolver.
    """
    response = await client.get(
        f"/api/v1/inventory/{inventory_movement.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"] == inventory_movement.id
    assert body["product_id"] == inventory_movement.product_id
    assert body["movement_type"] == inventory_movement.movement_type
    assert body["quantity"] == inventory_movement.quantity
    assert body["notes"] == inventory_movement.notes
    assert "created_at" in body


async def test_obtener_movimiento_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """GET /inventory/{id} con un id que no existe devuelve 404."""
    response = await client.get(
        "/api/v1/inventory/9999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_obtener_movimiento_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /inventory/{id} sin token devuelve 401."""
    response = await client.get("/api/v1/inventory/1")
    assert response.status_code == 401


# ============================================================
# POST /api/v1/inventory/ — Registrar movimiento
# ============================================================


async def test_registrar_entrada_actualiza_stock(
    client: httpx.AsyncClient,
    admin_token: str,
    product: Product,
):
    """
    POST /inventory/ con ENTRADA devuelve 201 y sube el stock del producto.

    El fixture `product` tiene stock=100. Registramos ENTRADA de 50.
    Verificamos:
    - El movimiento se creó con los datos correctos (status 201)
    - El stock del producto subió de 100 a 150

    ¿Por qué verificar el stock con un GET adicional?
    Porque el POST devuelve el movimiento, no el producto. Para confirmar
    que el efecto secundario (actualizar stock) ocurrió correctamente,
    consultamos el producto después del movimiento.
    """
    # Act: registrar la entrada
    response = await client.post(
        "/api/v1/inventory/",
        json={"product_id": product.id, "movement_type": "ENTRADA", "quantity": 50},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201

    body = response.json()
    assert body["product_id"] == product.id
    assert body["movement_type"] == "ENTRADA"
    assert body["quantity"] == 50
    assert "id" in body
    assert "created_at" in body

    # Verificar que el stock del producto subió
    product_response = await client.get(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert product_response.json()["stock"] == 150  # 100 + 50


async def test_registrar_salida_actualiza_stock(
    client: httpx.AsyncClient,
    admin_token: str,
    product: Product,
):
    """
    POST /inventory/ con SALIDA devuelve 201 y baja el stock del producto.

    El fixture `product` tiene stock=100. Registramos SALIDA de 30.
    El stock debe quedar en 70 (100 - 30).
    """
    response = await client.post(
        "/api/v1/inventory/",
        json={
            "product_id": product.id,
            "movement_type": "SALIDA",
            "quantity": 30,
            "notes": "Despacho pedido #42",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    assert response.json()["movement_type"] == "SALIDA"

    # Verificar que el stock bajó
    product_response = await client.get(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert product_response.json()["stock"] == 70  # 100 - 30


async def test_registrar_ajuste_fija_stock(
    client: httpx.AsyncClient,
    admin_token: str,
    product: Product,
):
    """
    POST /inventory/ con AJUSTE devuelve 201 y fija el stock al valor exacto.

    El fixture `product` tiene stock=100. Registramos AJUSTE de 42.
    El stock debe quedar en 42 (no 100+42, ni 100-42 — exactamente 42).
    Simula un conteo físico: "encontramos 42 unidades, ponlo en 42".
    """
    response = await client.post(
        "/api/v1/inventory/",
        json={
            "product_id": product.id,
            "movement_type": "AJUSTE",
            "quantity": 42,
            "notes": "Conteo físico mensual",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201

    # Verificar que el stock quedó en el valor exacto del ajuste
    product_response = await client.get(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert product_response.json()["stock"] == 42  # valor absoluto, no suma/resta


async def test_registrar_movimiento_como_empleado(
    client: httpx.AsyncClient,
    employee_token: str,
    product: Product,
):
    """
    POST /inventory/ con token de Empleado también devuelve 201.

    Los empleados son quienes físicamente reciben y despachan mercancía.
    Restringir esto al Administrador rompería el flujo real del negocio.
    """
    response = await client.post(
        "/api/v1/inventory/",
        json={"product_id": product.id, "movement_type": "ENTRADA", "quantity": 10},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 201


async def test_registrar_movimiento_sin_token_devuelve_401(
    client: httpx.AsyncClient, product: Product
):
    """POST /inventory/ sin token devuelve 401."""
    response = await client.post(
        "/api/v1/inventory/",
        json={"product_id": product.id, "movement_type": "ENTRADA", "quantity": 10},
    )
    assert response.status_code == 401


async def test_registrar_salida_stock_insuficiente_devuelve_400(
    client: httpx.AsyncClient,
    admin_token: str,
    product: Product,
):
    """
    POST /inventory/ con SALIDA mayor al stock disponible devuelve 400.

    El fixture `product` tiene stock=100.
    Intentamos sacar 150 — más de lo que hay.
    El servicio detecta que new_stock = 100 - 150 = -50 (negativo) y rechaza.

    ¿Por qué 400 y no 422?
    422 es para datos malformados (Pydantic). La cantidad=150 es un número
    válido — el problema es el ESTADO del sistema (stock insuficiente),
    no el formato del dato. Por eso es 400 Bad Request.
    """
    response = await client.post(
        "/api/v1/inventory/",
        json={"product_id": product.id, "movement_type": "SALIDA", "quantity": 150},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


async def test_registrar_movimiento_producto_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """POST /inventory/ con un product_id que no existe devuelve 404."""
    response = await client.post(
        "/api/v1/inventory/",
        json={"product_id": 9999, "movement_type": "ENTRADA", "quantity": 10},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_registrar_movimiento_producto_inactivo_devuelve_400(
    client: httpx.AsyncClient,
    admin_token: str,
    db: AsyncSession,
):
    """
    POST /inventory/ con un producto inactivo devuelve 400.

    Creamos el producto inactivo directamente en la BD para no depender
    del endpoint DELETE. El servicio verifica is_active y rechaza el movimiento.
    """
    # Arrange: crear un producto inactivo directamente en la BD de prueba
    inactive_product = Product(
        name="Producto Descontinuado",
        price=5000,
        stock=10,
        is_active=False,  # ← ya está inactivo desde el inicio
        created_at=datetime.now(UTC),
    )
    db.add(inactive_product)
    await db.commit()
    await db.refresh(inactive_product)

    # Act: intentar registrar un movimiento en ese producto
    response = await client.post(
        "/api/v1/inventory/",
        json={
            "product_id": inactive_product.id,
            "movement_type": "ENTRADA",
            "quantity": 10,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Assert: el servicio lo rechaza porque el producto está inactivo
    assert response.status_code == 400


async def test_registrar_movimiento_cantidad_invalida_devuelve_422(
    client: httpx.AsyncClient,
    admin_token: str,
    product: Product,
):
    """
    POST /inventory/ con quantity=0 devuelve 422 — Pydantic lo rechaza.

    InventoryMovementCreate tiene `quantity: int = Field(ge=1)`.
    ge=1 significa "greater than or equal to 1": la cantidad mínima es 1.
    Un movimiento de 0 unidades no tiene sentido de negocio.
    Pydantic intercepta quantity=0 antes de que llegue al servicio.
    """
    response = await client.post(
        "/api/v1/inventory/",
        json={"product_id": product.id, "movement_type": "ENTRADA", "quantity": 0},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422
