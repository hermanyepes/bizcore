# ============================================================
# BizCore — Servicio: lógica de agregación para Dashboard
# ============================================================
#
# ANALOGÍA: este archivo es el asistente del dueño del negocio.
# El dueño llega a las 8am y le dice: "necesito el reporte del día".
# El asistente va a la BD, hace los cálculos, y le trae
# el tablero listo. No modifica nada — solo lee y resume.
#
# ¿POR QUÉ UN SERVICIO Y NO DIRECTO EN EL ENDPOINT?
# El endpoint tiene un trabajo: hablar HTTP (recibir request,
# verificar JWT, devolver response). Si metes 5 queries de
# agregación ahí, el endpoint crece y mezcla responsabilidades.
# El servicio puede ser llamado desde múltiples lugares en el
# futuro (otro endpoint, una tarea programada, un email de reporte)
# sin duplicar las queries.
#
# ¿POR QUÉ NO EN EL CRUD?
# El CRUD opera sobre UNA tabla a la vez con operaciones simples
# (insertar, buscar por id, listar). Estas queries tocan varias
# tablas y usan funciones de agregación (COUNT, SUM, GROUP BY).
# Eso es lógica de negocio — no le corresponde al almacenero.
#
# ¿QUÉ ES func.coalesce(func.sum(...), 0)?
# Cuando no hay filas que sumar, SQL devuelve NULL (no cero).
# coalesce(NULL, 0) le dice a SQL: "si el resultado es NULL,
# devuelve 0 en su lugar". Sin esto, total_stock podría ser None
# y Pydantic rechazaría la respuesta (el tipo es int, no int|None).
#
# ============================================================

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.product import Product
from app.models.user import User
from app.schemas.dashboard import DashboardSummary, LowStockProduct

# Umbral de stock bajo: productos con stock MENOR a este valor
# aparecen en la lista roja del dashboard.
LOW_STOCK_THRESHOLD = 10

# Estados posibles de un pedido — deben coincidir con los
# valores Literal definidos en schemas/order.py.
# Los incluimos aquí para que orders_by_status siempre devuelva
# los cuatro estados, incluso si alguno tiene conteo cero.
ORDER_STATUSES = ["PENDIENTE", "COMPLETADO", "CANCELADO"]


async def get_dashboard_summary(db: AsyncSession) -> DashboardSummary:
    """
    Calcula y devuelve todas las métricas del dashboard en una sola llamada.

    Ejecuta 5 queries independientes contra la BD y ensambla
    el resultado en un objeto DashboardSummary.

    ¿Por qué 5 queries separadas y no un solo SELECT gigante?
    Cada métrica viene de una tabla diferente o tiene una lógica
    distinta. Separarlas hace el código legible y fácil de modificar.
    Un JOIN entre Users, Products y Orders solo para contar cosas
    distintas sería más confuso que eficiente.

    Parámetros:
    - db: sesión de BD inyectada por FastAPI vía Depends(get_db)
    """

    # ----------------------------------------------------------
    # Query 1: total de usuarios activos
    #
    # SELECT COUNT(*) FROM users WHERE is_active = TRUE
    #
    # select(func.count()): cuenta las filas que pasan el filtro.
    # .select_from(User): necesario cuando no hay columnas de User
    # en el SELECT (solo func.count()). Le dice a SQLAlchemy
    # qué tabla usar.
    # scalar(): extrae el único valor del resultado (un entero).
    # ----------------------------------------------------------
    result = await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)  # noqa: E712
    )
    total_active_users: int = result.scalar() or 0

    # ----------------------------------------------------------
    # Query 2: total de productos activos
    #
    # SELECT COUNT(*) FROM products WHERE is_active = TRUE
    # ----------------------------------------------------------
    result = await db.execute(
        select(func.count()).select_from(Product).where(Product.is_active == True)  # noqa: E712
    )
    total_active_products: int = result.scalar() or 0

    # ----------------------------------------------------------
    # Query 3: suma de stock de productos activos
    #
    # SELECT COALESCE(SUM(stock), 0) FROM products WHERE is_active = TRUE
    #
    # coalesce(..., 0): si no hay productos activos, SUM devuelve
    # NULL en SQL. coalesce lo convierte a 0. Sin esto, el campo
    # sería None y Pydantic lo rechazaría (tipo declarado: int).
    # ----------------------------------------------------------
    result = await db.execute(
        select(func.coalesce(func.sum(Product.stock), 0)).where(
            Product.is_active == True  # noqa: E712
        )
    )
    total_stock: int = result.scalar() or 0

    # ----------------------------------------------------------
    # Query 4: valor total del inventario
    #
    # SELECT COALESCE(SUM(stock * price), 0)
    # FROM products WHERE is_active = TRUE
    #
    # SQLAlchemy permite operar columnas directamente:
    # Product.stock * Product.price → SQL: stock * price
    # El resultado es Integer porque tanto stock como price son Integer.
    # (COP no tiene centavos → mismo criterio que price en Product)
    # ----------------------------------------------------------
    result = await db.execute(
        select(func.coalesce(func.sum(Product.stock * Product.price), 0)).where(
            Product.is_active == True  # noqa: E712
        )
    )
    total_inventory_value: int = result.scalar() or 0

    # ----------------------------------------------------------
    # Query 5: conteo de pedidos agrupados por status
    #
    # SELECT status, COUNT(id) FROM orders GROUP BY status
    #
    # fetchall(): devuelve todas las filas del resultado.
    # Cada fila es una tupla: (status, conteo)
    # Ejemplo: [("PENDIENTE", 3), ("COMPLETADO", 20), ("CANCELADO", 1)]
    #
    # ¿Por qué construimos el dict con ORDER_STATUSES como base?
    # Si no hay pedidos CANCELADOS, GROUP BY no incluye esa fila.
    # El dashboard siempre debe mostrar los 3 estados, aunque
    # alguno tenga cero. Empezamos con todos en 0 y luego
    # sobreescribimos con los valores reales de la BD.
    # ----------------------------------------------------------
    result = await db.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    )
    rows = result.fetchall()

    # Inicializar todos los estados en cero para garantizar
    # que el dashboard siempre muestre los 3 estados
    orders_by_status: dict[str, int] = {status: 0 for status in ORDER_STATUSES}

    # Sobreescribir con los valores reales que devolvió la BD
    for status, count in rows:
        orders_by_status[status] = count

    # ----------------------------------------------------------
    # Query 6: productos con stock bajo
    #
    # SELECT id, name, stock FROM products
    # WHERE is_active = TRUE AND stock < 10
    # ORDER BY stock ASC
    #
    # Seleccionamos solo las 3 columnas que necesita el dashboard.
    # ORDER BY stock ASC: el más crítico (menos stock) aparece primero.
    # Esto le da al dueño el diagnóstico más urgente de inmediato.
    #
    # fetchall(): devuelve una lista de tuplas (id, name, stock).
    # Convertimos cada tupla en un objeto LowStockProduct manualmente
    # porque no viene de un objeto ORM completo.
    # ----------------------------------------------------------
    result = await db.execute(
        select(Product.id, Product.name, Product.stock)
        .where(Product.is_active == True, Product.stock < LOW_STOCK_THRESHOLD)  # noqa: E712
        .order_by(Product.stock)
    )
    low_stock_rows = result.fetchall()

    # Construir la lista de LowStockProduct desde las tuplas
    low_stock_products = [
        LowStockProduct(id=row.id, name=row.name, stock=row.stock)
        for row in low_stock_rows
    ]

    # ----------------------------------------------------------
    # Ensamblar y devolver el resultado final
    #
    # Construimos el DashboardSummary con todos los valores
    # calculados en las queries anteriores.
    # ----------------------------------------------------------
    return DashboardSummary(
        total_active_users=total_active_users,
        total_active_products=total_active_products,
        total_stock=total_stock,
        total_inventory_value=total_inventory_value,
        orders_by_status=orders_by_status,
        low_stock_products=low_stock_products,
    )
