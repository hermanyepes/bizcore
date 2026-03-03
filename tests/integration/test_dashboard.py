# ============================================================
# BizCore — Tests de integración para Dashboard
# ============================================================
#
# ANALOGÍA: estos tests son el inspector de calidad del tablero.
# Antes de colgarlo en la pared de la oficina, el inspector
# revisa cada cajita: ¿muestra el número correcto? ¿funciona
# cuando la BD está vacía? ¿un empleado puede verlo?
#
# TESTS A CUBRIR:
#   1. Sin token → 401 (el tablero no es público)
#   2. BD casi vacía → ceros y listas vacías (sin errores)
#   3. Con datos reales → métricas correctas
#   4. Producto con stock < 10 → aparece en low_stock_products
#   5. Empleado (no solo admin) → puede ver el tablero
#
# FIXTURES QUE SE USAN (definidas en tests/conftest.py):
#   client        → cliente HTTP con BD de prueba inyectada
#   db            → sesión de BD compartida con el cliente
#   admin_user    → usuario Administrador en la BD de prueba
#   employee_user → usuario Empleado en la BD de prueba
#   admin_token   → JWT válido de admin (llama al login real)
#   employee_token→ JWT válido de empleado
#   product       → Café Especial, stock=100, price=15000
#   order         → pedido PENDIENTE (depende de product + admin_user + supplier)
#
# ============================================================

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


# ============================================================
# Test 1: sin token → 401
# ============================================================
async def test_get_summary_requires_auth(client: AsyncClient) -> None:
    """
    El endpoint rechaza requests sin token JWT.

    Sin Depends(get_current_user) en el endpoint, este test fallaría
    (devolvería 200 en vez de 401). Confirma que el portero funciona.
    """
    response = await client.get("/api/v1/dashboard/summary")

    assert response.status_code == 401


# ============================================================
# Test 2: BD casi vacía → todos los conteos en cero
# ============================================================
async def test_get_summary_empty_db(
    client: AsyncClient,
    admin_token: str,
) -> None:
    """
    Cuando no hay productos ni pedidos, el dashboard devuelve
    ceros y listas vacías — sin errores ni None.

    DATOS EN BD AL CORRER ESTE TEST:
    - 1 usuario activo (el admin que creó admin_token)
    - 0 productos
    - 0 pedidos

    ¿Por qué total_active_users es 1 y no 0?
    admin_token depende de admin_user, que crea el admin en la BD.
    No hay productos ni pedidos porque no se usaron esos fixtures.

    Este test verifica que coalesce funciona correctamente:
    SUM sobre tabla vacía → NULL en SQL → 0 en Python (no None).
    Si faltara coalesce, Pydantic rechazaría la respuesta con un error.

    También verifica que orders_by_status inicializa los 3 estados en cero
    aunque GROUP BY no devuelva ninguna fila (no hay pedidos).
    """
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()

    # El admin existe → 1 usuario activo
    assert data["total_active_users"] == 1

    # No hay productos ni pedidos
    assert data["total_active_products"] == 0
    assert data["total_stock"] == 0
    assert data["total_inventory_value"] == 0

    # Los 3 estados deben aparecer aunque no haya pedidos
    assert data["orders_by_status"] == {
        "PENDIENTE": 0,
        "COMPLETADO": 0,
        "CANCELADO": 0,
    }

    # Sin productos no puede haber lista roja
    assert data["low_stock_products"] == []


# ============================================================
# Test 3: con datos reales → métricas correctas
# ============================================================
async def test_get_summary_with_data(
    client: AsyncClient,
    admin_token: str,
    product: Product,
    order: object,
) -> None:
    """
    Con un producto y un pedido en la BD, las métricas reflejan
    exactamente esos datos.

    DATOS EN BD AL CORRER ESTE TEST:
    - 1 usuario activo (admin, creado por admin_token → admin_user)
    - 1 producto activo: Café Especial, stock=100, price=15000
    - 1 pedido: status="PENDIENTE"
    - 1 proveedor (lo crea el fixture `order` → `supplier`)

    CÁLCULOS ESPERADOS:
    - total_stock = 100
    - total_inventory_value = 100 × 15000 = 1.500.000
    - orders_by_status["PENDIENTE"] = 1
    - low_stock_products = [] (stock=100 ≥ 10)

    ¿Por qué `order` como parámetro aunque no lo usemos directamente?
    Al declararlo como fixture, pytest lo ejecuta y crea el pedido
    en la BD antes de que corra el test. No necesitamos el objeto
    Python — solo necesitamos que exista la fila en la BD.
    """
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_active_users"] == 1
    assert data["total_active_products"] == 1
    assert data["total_stock"] == 100
    assert data["total_inventory_value"] == 1_500_000

    assert data["orders_by_status"]["PENDIENTE"] == 1
    assert data["orders_by_status"]["COMPLETADO"] == 0
    assert data["orders_by_status"]["CANCELADO"] == 0

    # stock=100 → no aparece en la lista roja (umbral es < 10)
    assert data["low_stock_products"] == []


# ============================================================
# Test 4: producto con stock bajo → aparece en low_stock_products
# ============================================================
async def test_get_summary_low_stock_products(
    client: AsyncClient,
    admin_token: str,
    admin_user: object,
    db: AsyncSession,
) -> None:
    """
    Un producto activo con stock < 10 aparece en la lista roja.

    Insertamos el producto directamente en la BD (sin pasar por
    POST /products) para no hacer que este test dependa del
    endpoint de creación — mismo patrón que los demás fixtures.

    DATOS EN BD AL CORRER ESTE TEST:
    - 1 usuario activo (admin)
    - 1 producto: stock=3 → debe aparecer en low_stock_products
    """
    # Insertamos el producto de stock crítico directamente en la BD
    low_product = Product(
        name="Producto Crítico",
        price=5000,
        stock=3,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(low_product)
    await db.commit()
    await db.refresh(low_product)

    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()

    # El producto con stock=3 debe aparecer en la lista roja
    assert len(data["low_stock_products"]) == 1

    item = data["low_stock_products"][0]
    assert item["id"] == low_product.id
    assert item["name"] == "Producto Crítico"
    assert item["stock"] == 3


# ============================================================
# Test 5: empleado también puede ver el dashboard
# ============================================================
async def test_get_summary_employee_can_access(
    client: AsyncClient,
    employee_token: str,
) -> None:
    """
    Un usuario con rol Empleado puede ver el dashboard.

    El endpoint acepta cualquier JWT válido, sin importar el rol.
    Este test confirma que no hay restricción de rol accidental
    (por ejemplo, si alguien agrega un check de Administrador).

    Solo verificamos el status code — el contenido ya lo probamos
    en los tests anteriores.
    """
    response = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 200
