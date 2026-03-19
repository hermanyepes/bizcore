# ============================================================
# BizCore — CRUD: operaciones de base de datos para InventoryMovement
# ============================================================
#
# ANALOGÍA: este archivo es el bodeguero del libro de registro.
# Solo habla con PostgreSQL. No valida permisos, no actualiza stock,
# no toma decisiones de negocio. Solo recibe instrucciones y ejecuta:
# anota un movimiento, tráeme un movimiento, tráeme la lista.
#
# ¿POR QUÉ NO HAY update NI delete?
# Los movimientos de inventario son INMUTABLES por diseño.
# Si hay un error, el servicio crea un movimiento corrector.
# El bodeguero nunca borra ni edita páginas de su libro.
#
# ¿QUIÉN ACTUALIZA `product.stock`?
# El servicio (services/inventory.py), no este CRUD.
# Este archivo solo escribe en la tabla `inventory_movements`.
# La separación es intencional: CRUD = operación de BD pura,
# servicio = lógica de negocio que coordina varias operaciones.
#
# ============================================================

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_paginated
from app.models.inventory_movement import InventoryMovement
from app.schemas.inventory_movement import InventoryMovementCreate

# ============================================================
# GET — Consultas de lectura
# ============================================================


async def get_movement_by_id(
    db: AsyncSession,
    movement_id: int,
) -> InventoryMovement | None:
    """
    Busca un movimiento de inventario por su ID.

    Devuelve el objeto InventoryMovement si existe, None si no.
    El endpoint usa este resultado para devolver 404 si es None.
    """
    result = await db.execute(
        select(InventoryMovement).where(InventoryMovement.id == movement_id)
    )
    return result.scalar_one_or_none()


async def get_movements(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    product_id: int | None = None,
    movement_type: str | None = None,
) -> tuple[list[InventoryMovement], int]:
    """
    Devuelve una página de movimientos + el total de registros.

    ¿Para qué sirve `product_id` opcional?
    Permite filtrar el historial de un producto específico.
    Si se envía, devuelve solo los movimientos de ese producto.
    Si no se envía (None), devuelve todos los movimientos del sistema.

    Esto permite dos endpoints con la misma función:
      GET /api/v1/inventory              → todos los movimientos
      GET /api/v1/inventory?product_id=5 → solo movimientos del producto 5

    ¿Por qué skip/limit en vez de page/page_size?
    Mismo criterio que en get_products: skip y limit son los parámetros
    nativos de SQL (OFFSET y LIMIT). La conversión la hace el endpoint.
      skip = (page - 1) * page_size

    ¿Por qué dos queries?
    1. "Dame los movimientos de esta página" → select con limit/offset
    2. "¿Cuántos movimientos hay en total?"  → select count(*)
    Sin el total no podemos calcular cuántas páginas existen.

    ¿Por qué ordenamos por created_at DESC?
    El movimiento más reciente primero — igual que un extracto bancario.
    El usuario quiere ver lo último que pasó, no lo primero del año 2024.
    """
    # Construir la lista de filtros opcionales.
    # get_paginated los aplica a base_query y count_query en el mismo loop.
    filters = []
    if product_id is not None:
        filters.append(InventoryMovement.product_id == product_id)
    # movement_type: 'ENTRADA' | 'SALIDA' | None (todos los tipos)
    if movement_type is not None:
        filters.append(InventoryMovement.movement_type == movement_type)

    # Ordenamos del más reciente al más viejo — como un extracto bancario.
    # order_by solo afecta base_query; el COUNT ignora el orden.
    return await get_paginated(
        db,
        InventoryMovement,
        skip,
        limit,
        filters,
        order_by=InventoryMovement.created_at.desc(),
    )


# ============================================================
# CREATE — Inserción
# ============================================================


async def create_movement(
    db: AsyncSession,
    data: InventoryMovementCreate,
    created_by_id: str,
) -> InventoryMovement:
    """
    Registra un nuevo movimiento de inventario en la BD.

    ¿Por qué `created_by_id` es un parámetro separado y no parte del schema?
    Porque el cliente no debe poder elegir quién "firmó" el movimiento.
    El endpoint extrae ese valor del JWT del usuario logueado y lo pasa
    aquí directamente. El schema InventoryMovementCreate no lo incluye.

    Flujo:
    1. Construimos el objeto InventoryMovement con los datos del schema
       + el created_by_id que viene del token JWT
    2. db.add() lo agrega a la sesión (en memoria, aún no en la BD)
    3. db.commit() ejecuta el INSERT en PostgreSQL
    4. db.refresh() recarga el objeto para obtener id y created_at
       generados por el servidor

    IMPORTANTE: esta función SOLO crea el registro del movimiento.
    NO actualiza product.stock. Esa responsabilidad es del servicio
    (services/inventory.py) que llama a esta función.
    """
    movement = InventoryMovement(
        product_id=data.product_id,
        movement_type=data.movement_type,
        quantity=data.quantity,
        notes=data.notes,
        created_by_id=created_by_id,
        # id y created_at los genera PostgreSQL automáticamente
    )
    db.add(movement)
    await db.commit()
    await db.refresh(movement)
    return movement
