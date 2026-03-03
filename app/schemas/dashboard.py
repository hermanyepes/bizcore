# ============================================================
# BizCore — Schemas Pydantic para Dashboard
# ============================================================
#
# ANALOGÍA: si el endpoint del dashboard es el tablero en la
# pared del dueño, estos schemas son el DISEÑO del tablero:
# qué cajitas tiene, qué tipo de número va en cada una,
# cuántas secciones hay.
#
# DIFERENCIA con otros schemas del proyecto:
#   - ProductCreate / ProductUpdate → formularios de ENTRADA (el cliente envía datos)
#   - DashboardSummary              → formulario de SALIDA PURO (solo lectura)
#
# No hay DashboardCreate ni DashboardUpdate porque el dashboard
# no se "crea" ni se "modifica" — es una foto calculada en tiempo real.
#
# ¿POR QUÉ TRES SCHEMAS EN VEZ DE UNO?
# La respuesta tiene partes con estructuras distintas:
#   - Los totales son números simples → van directos en DashboardSummary
#   - orders_by_status es un diccionario (status → cantidad)
#   - low_stock_products es una lista de objetos con 3 campos cada uno
#
# Tener LowStockProduct como schema separado permite que Pydantic
# valide y documente cada ítem de la lista individualmente.
# ============================================================

from pydantic import BaseModel


class LowStockProduct(BaseModel):
    """
    Representa un producto con stock bajo en el dashboard.

    ANALOGÍA: cada fila de la "lista roja" en el tablero —
    nombre del producto y cuántas unidades quedan.

    ¿Por qué solo id, name y stock?
    El dashboard necesita que el dueño identifique el producto
    (id + name) y sepa qué tan urgente es (stock).
    El precio, la categoría y otros campos no aportan al diagnóstico.
    Menos información → tablero más legible.

    ¿Por qué NO tiene model_config = ConfigDict(from_attributes=True)?
    Este objeto NO se construye desde una fila ORM completa.
    El servicio va a construirlo manualmente a partir de los
    resultados de una query de agregación — veremos eso en
    services/dashboard.py.
    """

    id: int       # identificador del producto (para enlazar si la UI lo necesita)
    name: str     # nombre para mostrar en el tablero
    stock: int    # unidades disponibles (siempre < 10 por definición)


class DashboardSummary(BaseModel):
    """
    Respuesta completa del endpoint GET /api/v1/dashboard/summary.

    ANALOGÍA: es el tablero completo — todas las cajitas juntas.

    Campos:
    - total_active_users     → usuarios con is_active=True
    - total_active_products  → productos con is_active=True
    - total_stock            → suma de stock de todos los productos activos
    - total_inventory_value  → suma de (stock × price) de productos activos
    - orders_by_status       → conteo de pedidos agrupados por status
    - low_stock_products     → lista de productos activos con stock < 10

    ¿Por qué total_inventory_value es int y no float?
    Mismo criterio que price en Product: en Colombia el peso (COP)
    no tiene centavos. Un Float introduciría decimales ficticios
    (ej: 4200000.0000001) que son matemáticamente incorrectos
    para esta moneda. Integer es honesto con el dominio.

    ¿Por qué orders_by_status es dict[str, int] y no un schema aparte?
    Los posibles valores (PENDIENTE, EN_PROCESO, ENTREGADO, CANCELADO)
    ya están definidos en el modelo Order. Un diccionario es suficiente
    aquí: la clave es el nombre del status, el valor es el conteo.
    Pydantic valida que las claves sean strings y los valores enteros.
    """

    total_active_users: int
    total_active_products: int
    total_stock: int
    total_inventory_value: int

    # Ejemplo de valor esperado:
    # {"PENDIENTE": 3, "EN_PROCESO": 7, "ENTREGADO": 20, "CANCELADO": 1}
    orders_by_status: dict[str, int]

    # Lista de productos activos con stock < 10, ordenada por stock ascendente
    # (el más crítico primero — el que tiene menos stock aparece primero)
    low_stock_products: list[LowStockProduct]
