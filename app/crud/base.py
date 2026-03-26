# ============================================================
# BizCore — CRUD: helpers genéricos compartidos por todos los módulos
# ============================================================
#
# ANALOGÍA: este archivo es el chef central de la cocina.
# Cada bodeguero (user.py, product.py, supplier.py...) sabe
# qué ingredientes necesita (los filtros), pero la receta de
# "cómo paginar" siempre la ejecuta el chef central.
# Así, si la receta cambia, solo se cambia aquí.
#
# ============================================================

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ClauseElement


async def get_paginated[T](
    db: AsyncSession,
    model: type[T],
    skip: int,
    limit: int,
    filters: list | None = None,
    order_by: ClauseElement | None = None,
    options: list | None = None,
) -> tuple[list[T], int]:
    """
    Ejecuta dos queries con los mismos filtros y devuelve (items, total).

    ¿Por qué dos queries y no una sola?
    SQL no puede hacer .offset/.limit Y contar el total al mismo
    tiempo. Necesitamos:
    - Query 1 (base_query): trae los N registros de esta página.
    - Query 2 (count_query): cuenta TODOS los registros que
      coinciden con los filtros, ignorando offset/limit.
    El frontend usa `total` para calcular cuántas páginas mostrar.

    Parámetros:
    - db:       sesión de base de datos (AsyncSession de SQLAlchemy)
    - model:    la clase del modelo (User, Product, Supplier...)
    - skip:     cuántos registros saltar (= página * tamaño_página)
    - limit:    cuántos registros traer (tamaño de página)
    - filters:  lista de condiciones SQLAlchemy ya construidas.
                Cada elemento es una expresión como:
                Product.is_active == True
                Product.category == "Bebidas"
                Si es None o lista vacía, no se aplica ningún filtro.
    - order_by: columna para ordenar la página (solo base_query).
                Ejemplo: InventoryMovement.created_at.desc()
                No aplica al COUNT — el orden no afecta el total.
    - options:  opciones de carga de relaciones (solo base_query).
                Ejemplo: [selectinload(Order.items)]
                El COUNT nunca necesita cargar relaciones.

    Retorna:
    - Una tupla (items, total) donde:
      - items: lista de objetos del modelo para esta página
      - total: cantidad total de registros que coinciden con los filtros
    """
    # Construir las dos queries base — sin filtros aún
    base_query = select(model)
    count_query = select(func.count()).select_from(model)

    # Aplicar cada filtro a AMBAS queries en el mismo loop.
    # Esta es la clave del helper: es imposible olvidarse de
    # aplicar un filtro a count_query, porque siempre van juntas.
    for f in filters or []:
        base_query = base_query.where(f)
        count_query = count_query.where(f)

    # Opciones de carga de relaciones — solo en base_query.
    # count_query nunca necesita cargar relaciones: solo cuenta filas.
    for opt in options or []:
        base_query = base_query.options(opt)

    # Orden — solo en base_query.
    # El total no cambia según el orden, así que count_query lo ignora.
    if order_by is not None:
        base_query = base_query.order_by(order_by)

    # Query 1: los registros de esta página (con offset y limit)
    items_result = await db.execute(base_query.offset(skip).limit(limit))
    items = list(items_result.scalars().all())

    # Query 2: el total de registros que coinciden (sin offset ni limit)
    total = (await db.execute(count_query)).scalar_one()

    return items, total
