# ============================================================
# BizCore — Tests de integración: Órdenes de Compra
# ============================================================
#
# Cada test prueba un endpoint real de /api/v1/orders con:
#   - BD SQLite en memoria (aislada por test via conftest.py)
#   - Cliente HTTP en memoria (sin abrir un puerto real)
#   - JWT real generado por el endpoint de login
#
# COBERTURA:
#   GET  /orders/          → 3 tests (200, 401, filtro por proveedor)
#   GET  /orders/{id}      → 3 tests (200 con items, 401, 404)
#   POST /orders/          → 11 tests (happy path, snapshot, stock, permisos, errores)
#   PUT  /orders/{id}      → 3 tests (200, 403, 404)
#   DELETE /orders/{id}    → 3 tests (200, 403, 404)
#
# TOTAL: 23 tests
#
# ============================================================

from datetime import UTC, datetime

from httpx import AsyncClient

from app.models.order import Order
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User

# ============================================================
# GET /api/v1/orders — Listar pedidos
# ============================================================


async def test_listar_pedidos_autenticado_devuelve_200(
    client: AsyncClient,
    admin_token: str,
    order: Order,
) -> None:
    """
    Un usuario autenticado puede listar pedidos.
    La respuesta incluye el pedido creado por el fixture con sus ítems.
    """
    response = await client.get(
        "/api/v1/orders/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "items" in data
    # Verificar que el primer pedido tiene la estructura correcta
    primer_pedido = data["items"][0]
    assert "id" in primer_pedido
    assert "status" in primer_pedido
    assert "items" in primer_pedido  # los ítems anidados deben estar presentes


async def test_listar_pedidos_sin_token_devuelve_401(
    client: AsyncClient,
) -> None:
    """Sin token JWT, el endpoint rechaza la petición con 401."""
    response = await client.get("/api/v1/orders/")
    assert response.status_code == 401


async def test_listar_pedidos_filtro_por_proveedor(
    client: AsyncClient,
    admin_token: str,
    db,
    supplier: Supplier,
    admin_user: User,
) -> None:
    """
    El parámetro ?supplier_id= filtra correctamente los pedidos.
    Solo deben aparecer los pedidos del proveedor solicitado.
    """
    # Crear un segundo proveedor directamente en la BD
    second_supplier = Supplier(
        name="Segundo Proveedor SA",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(second_supplier)
    await db.commit()
    await db.refresh(second_supplier)

    # Crear un pedido para el proveedor original (sin ítems — solo para el filtro)
    order_supplier_1 = Order(
        supplier_id=supplier.id,
        created_by_id=admin_user.document_id,
        status="PENDIENTE",
        created_at=datetime.now(UTC),
    )
    # Crear un pedido para el segundo proveedor
    order_supplier_2 = Order(
        supplier_id=second_supplier.id,
        created_by_id=admin_user.document_id,
        status="PENDIENTE",
        created_at=datetime.now(UTC),
    )
    db.add(order_supplier_1)
    db.add(order_supplier_2)
    await db.commit()

    # Filtrar por el proveedor original — solo debe aparecer 1 pedido
    response = await client.get(
        f"/api/v1/orders/?supplier_id={supplier.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["supplier_id"] == supplier.id


# ============================================================
# GET /api/v1/orders/{id} — Obtener un pedido
# ============================================================


async def test_obtener_pedido_devuelve_200_con_items_anidados(
    client: AsyncClient,
    admin_token: str,
    order: Order,
) -> None:
    """
    GET /{id} devuelve el pedido completo con sus ítems anidados.
    Verifica que la estructura JSON incluye items con todos sus campos.
    """
    response = await client.get(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order.id
    assert data["status"] == "PENDIENTE"
    # Verificar que los ítems están anidados correctamente
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["quantity"] == 2
    assert item["unit_price"] == order.items[0].unit_price
    assert item["subtotal"] == order.items[0].subtotal
    assert item["product_id"] == order.items[0].product_id


async def test_obtener_pedido_sin_token_devuelve_401(
    client: AsyncClient,
    order: Order,
) -> None:
    """Sin token JWT, el endpoint rechaza la petición con 401."""
    response = await client.get(f"/api/v1/orders/{order.id}")
    assert response.status_code == 401


async def test_obtener_pedido_inexistente_devuelve_404(
    client: AsyncClient,
    admin_token: str,
) -> None:
    """Un ID que no existe en la BD devuelve 404."""
    response = await client.get(
        "/api/v1/orders/99999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


# ============================================================
# POST /api/v1/orders — Crear pedido
# ============================================================


async def test_crear_pedido_devuelve_201(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
    product: Product,
) -> None:
    """
    Happy path: crear un pedido con un ítem devuelve 201.
    La respuesta incluye el encabezado y los ítems anidados.
    """
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "notes": "Pedido de prueba",
            "items": [{"product_id": product.id, "quantity": 5}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["supplier_id"] == supplier.id
    assert data["status"] == "PENDIENTE"
    assert data["notes"] == "Pedido de prueba"
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 5


async def test_crear_pedido_snapshot_precio_y_subtotal_correcto(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
    product: Product,
) -> None:
    """
    El sistema copia el precio actual del producto (snapshot) y calcula
    el subtotal correctamente. El cliente no controla estos valores.

    product.price = 15000 (definido en el fixture de conftest)
    quantity = 3
    Esperado: unit_price = 15000, subtotal = 45000
    """
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": product.id, "quantity": 3}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["unit_price"] == product.price           # snapshot correcto
    assert item["subtotal"] == product.price * 3         # 15000 × 3 = 45000


async def test_crear_pedido_decrementa_stock_del_producto(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
    product: Product,
) -> None:
    """
    Después de crear un pedido, el stock del producto debe haberse
    decrementado en la cantidad solicitada.

    stock inicial: 100 (definido en el fixture de conftest)
    quantity pedida: 10
    stock esperado después: 90
    """
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": product.id, "quantity": 10}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201

    # Verificar el stock actualizado consultando el producto
    product_response = await client.get(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert product_response.status_code == 200
    assert product_response.json()["stock"] == 90  # 100 - 10


async def test_crear_pedido_como_empleado_devuelve_201(
    client: AsyncClient,
    employee_token: str,
    supplier: Supplier,
    product: Product,
) -> None:
    """
    Los empleados también pueden crear pedidos — no solo los admins.
    Crear un pedido es una operación operativa, no solo administrativa.
    """
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": product.id, "quantity": 1}],
        },
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 201


async def test_crear_pedido_sin_token_devuelve_401(
    client: AsyncClient,
    supplier: Supplier,
    product: Product,
) -> None:
    """Sin token JWT, el endpoint rechaza la petición con 401."""
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": product.id, "quantity": 1}],
        },
    )
    assert response.status_code == 401


async def test_crear_pedido_proveedor_inexistente_devuelve_404(
    client: AsyncClient,
    admin_token: str,
    product: Product,
) -> None:
    """Si el supplier_id no existe en la BD, el servicio devuelve 404."""
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": 99999,
            "items": [{"product_id": product.id, "quantity": 1}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_crear_pedido_producto_inexistente_devuelve_404(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
) -> None:
    """Si un product_id en los ítems no existe en la BD, devuelve 404."""
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": 99999, "quantity": 1}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_crear_pedido_proveedor_inactivo_devuelve_400(
    client: AsyncClient,
    admin_token: str,
    db,
    product: Product,
) -> None:
    """No se puede crear un pedido para un proveedor inactivo (soft-deleted)."""
    # Crear un proveedor inactivo directamente en la BD
    inactive_supplier = Supplier(
        name="Proveedor Inactivo SA",
        is_active=False,
        created_at=datetime.now(UTC),
    )
    db.add(inactive_supplier)
    await db.commit()
    await db.refresh(inactive_supplier)

    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": inactive_supplier.id,
            "items": [{"product_id": product.id, "quantity": 1}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


async def test_crear_pedido_producto_inactivo_devuelve_400(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
    db,
) -> None:
    """No se puede pedir un producto inactivo (soft-deleted)."""
    # Crear un producto inactivo directamente en la BD
    inactive_product = Product(
        name="Producto Descontinuado",
        price=5000,
        stock=10,
        is_active=False,
        created_at=datetime.now(UTC),
    )
    db.add(inactive_product)
    await db.commit()
    await db.refresh(inactive_product)

    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": inactive_product.id, "quantity": 1}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


async def test_crear_pedido_stock_insuficiente_devuelve_400(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
    product: Product,
) -> None:
    """
    Si la cantidad solicitada supera el stock disponible, devuelve 400.

    product.stock = 100 (fixture), solicitamos 999.
    El servicio detecta esto antes de tocar la BD.
    """
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": product.id, "quantity": 999}],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400
    assert "Stock insuficiente" in response.json()["detail"]


async def test_crear_pedido_lista_items_vacia_devuelve_422(
    client: AsyncClient,
    admin_token: str,
    supplier: Supplier,
) -> None:
    """
    Una lista de ítems vacía falla con 422 (validación Pydantic).
    OrderCreate tiene min_length=1 en el campo `items`.
    Pydantic rechaza esto antes de llegar al servicio.
    """
    response = await client.post(
        "/api/v1/orders/",
        json={
            "supplier_id": supplier.id,
            "items": [],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


# ============================================================
# PUT /api/v1/orders/{id} — Actualizar pedido
# ============================================================


async def test_actualizar_status_pedido_como_admin(
    client: AsyncClient,
    admin_token: str,
    order: Order,
) -> None:
    """
    El administrador puede cambiar el status de un pedido.
    La respuesta devuelve el pedido con el status actualizado.
    """
    response = await client.put(
        f"/api/v1/orders/{order.id}",
        json={"status": "COMPLETADO"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETADO"
    assert data["id"] == order.id
    # Los ítems deben seguir presentes después del update
    assert len(data["items"]) == 1


async def test_actualizar_pedido_como_empleado_devuelve_403(
    client: AsyncClient,
    employee_token: str,
    order: Order,
) -> None:
    """
    Un Empleado no puede cambiar el status de un pedido.
    Solo el Administrador puede aprobar o completar pedidos.
    """
    response = await client.put(
        f"/api/v1/orders/{order.id}",
        json={"status": "COMPLETADO"},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_actualizar_pedido_inexistente_devuelve_404(
    client: AsyncClient,
    admin_token: str,
) -> None:
    """Intentar actualizar un pedido que no existe devuelve 404."""
    response = await client.put(
        "/api/v1/orders/99999",
        json={"status": "COMPLETADO"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


# ============================================================
# DELETE /api/v1/orders/{id} — Cancelar pedido
# ============================================================


async def test_cancelar_pedido_como_admin(
    client: AsyncClient,
    admin_token: str,
    order: Order,
) -> None:
    """
    El administrador puede cancelar un pedido.
    La respuesta devuelve el pedido con status="CANCELADO".
    El pedido sigue en la BD (no es un hard delete).
    """
    response = await client.delete(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELADO"
    assert data["id"] == order.id

    # Verificar que el pedido sigue en la BD (no fue borrado)
    get_response = await client.get(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "CANCELADO"


async def test_cancelar_pedido_como_empleado_devuelve_403(
    client: AsyncClient,
    employee_token: str,
    order: Order,
) -> None:
    """Un Empleado no puede cancelar pedidos. Solo el Administrador."""
    response = await client.delete(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_cancelar_pedido_inexistente_devuelve_404(
    client: AsyncClient,
    admin_token: str,
) -> None:
    """Intentar cancelar un pedido que no existe devuelve 404."""
    response = await client.delete(
        "/api/v1/orders/99999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


# ============================================================
# Validación de parámetros de paginación
# ============================================================


async def test_listar_pedidos_page_cero_devuelve_422(
    client: AsyncClient, admin_token: str
):
    """GET /orders?page=0 debe devolver 422 (mínimo es 1)."""
    response = await client.get(
        "/api/v1/orders/?page=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_listar_pedidos_page_size_cero_devuelve_422(
    client: AsyncClient, admin_token: str
):
    """GET /orders?page_size=0 debe devolver 422 (mínimo es 1)."""
    response = await client.get(
        "/api/v1/orders/?page_size=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_listar_pedidos_page_size_excesivo_devuelve_422(
    client: AsyncClient, admin_token: str
):
    """GET /orders?page_size=101 debe devolver 422 (máximo es 100)."""
    response = await client.get(
        "/api/v1/orders/?page_size=101",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


# ============================================================
# Filtros de listado
# ============================================================


async def test_filtrar_pedidos_por_status(
    client: AsyncClient,
    admin_token: str,
    order: Order,
) -> None:
    """
    GET /orders/?status=PENDIENTE devuelve solo pedidos con ese status.

    El fixture `order` crea un pedido con status=PENDIENTE.
    Filtramos por ese status y verificamos que todos los ítems coincidan.
    """
    response = await client.get(
        "/api/v1/orders/?status=PENDIENTE",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 1
    # Todos los pedidos devueltos deben tener el status solicitado
    for item in data["items"]:
        assert item["status"] == "PENDIENTE"


async def test_filtrar_pedidos_status_inexistente_devuelve_lista_vacia(
    client: AsyncClient,
    admin_token: str,
    order: Order,
) -> None:
    """
    GET /orders/?status=COMPLETADO cuando solo hay pedidos PENDIENTE
    devuelve total=0 e items=[].

    El fixture solo crea un pedido PENDIENTE. Buscar COMPLETADO no debe encontrar nada.
    """
    response = await client.get(
        "/api/v1/orders/?status=COMPLETADO",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
