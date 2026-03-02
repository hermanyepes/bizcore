# ============================================================
# BizCore — CRUD: operaciones de base de datos para Product
# ============================================================
#
# ANALOGÍA: este archivo es el bodeguero.
# Solo habla con PostgreSQL. No valida permisos, no toma
# decisiones de negocio, no sabe si el usuario tiene sesión.
# Solo recibe instrucciones y ejecuta: guarda, trae, actualiza.
#
# Cada función recibe `db` (la sesión de BD) como primer
# parámetro. FastAPI la inyecta automáticamente vía Depends(get_db).
#
# ============================================================

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate

# ============================================================
# GET — Consultas de lectura
# ============================================================


async def get_product_by_id(db: AsyncSession, product_id: int) -> Product | None:
    """
    Busca un producto por su id numérico.

    Devuelve el objeto Product si existe, None si no.
    El endpoint usa este resultado para devolver 404 si es None.
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_name(db: AsyncSession, name: str) -> Product | None:
    """
    Busca un producto por su nombre exacto.

    ¿Para qué sirve esta función?
    Para verificar duplicados antes de crear o renombrar un producto.
    Si ya existe un producto con ese nombre, el endpoint devuelve 409.
    El nombre es único en la BD (unique=True en el modelo), pero es
    mejor detectarlo aquí y devolver un mensaje claro que dejar que
    PostgreSQL lance un error críptico de constraint violation.
    """
    result = await db.execute(
        select(Product).where(Product.name == name)
    )
    return result.scalar_one_or_none()


async def get_products(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
) -> tuple[list[Product], int]:
    """
    Devuelve una página de productos activos + el total de registros activos.

    ¿Por qué skip y limit y no page y page_size?
    skip y limit son los parámetros nativos de SQL (OFFSET y LIMIT).
    La conversión de page → skip la hace el endpoint:
        skip = (page - 1) * page_size

    ¿Por qué filtramos is_active=True?
    Los productos desactivados (soft delete) no deben aparecer en el
    catálogo. Son invisibles para el cliente, pero siguen en la BD.

    ¿Por qué dos queries?
    Son dos preguntas distintas a la BD:
    1. "Dame los productos de esta página" → select con limit/offset
    2. "¿Cuántos productos activos hay en total?" → select count(*)
    Sin el total no podemos calcular cuántas páginas existen.
    """
    # Query 1: los productos activos de esta página
    products_result = await db.execute(
        select(Product)
        .where(Product.is_active == True)  # noqa: E712
        .offset(skip)
        .limit(limit)
    )
    products = list(products_result.scalars().all())

    # Query 2: el total de productos activos en la BD
    count_result = await db.execute(
        select(func.count())
        .select_from(Product)
        .where(Product.is_active == True)  # noqa: E712
    )
    total = count_result.scalar_one()

    return products, total


# ============================================================
# CREATE — Inserción
# ============================================================


async def create_product(db: AsyncSession, data: ProductCreate) -> Product:
    """
    Crea un nuevo producto en la BD.

    A diferencia de create_user, aquí no hay contraseña que hashear.
    El flujo es directo:
    1. Construimos el objeto Product con los datos del schema
    2. db.add() lo agrega a la sesión (en memoria, aún no en la BD)
    3. db.commit() ejecuta el INSERT en PostgreSQL
    4. db.refresh() recarga el objeto desde la BD para obtener
       los valores generados por el servidor (id, created_at)

    ¿Por qué db.refresh() después del commit?
    Porque antes del commit, `product.id` es None — PostgreSQL
    aún no asignó el número autoincremental. Después del refresh,
    `product.id` tiene el valor real (1, 2, 3...).
    """
    product = Product(
        name=data.name,
        description=data.description,
        price=data.price,
        stock=data.stock,
        category=data.category,
        # id y created_at los genera PostgreSQL automáticamente
        # is_active empieza en True por el default del modelo
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# ============================================================
# UPDATE — Actualización parcial
# ============================================================


async def update_product(
    db: AsyncSession,
    product_id: int,
    data: ProductUpdate,
) -> Product | None:
    """
    Actualiza solo los campos que el cliente envió.

    ¿Por qué exclude_unset=True?
    ProductUpdate tiene todos los campos como opcionales (None por defecto).
    Si el cliente solo envía {"price": 25000}, model_dump() sin
    exclude_unset devolvería también name=None, stock=None, etc.,
    sobreescribiendo datos que el cliente no quería cambiar.
    exclude_unset=True filtra solo los campos que realmente llegaron.

    ¿Qué hace setattr(product, field, value)?
    Es Python puro. Equivale a: product.price = 25000
    Pero de forma dinámica, sin saber de antemano qué campo es.
    Sin setattr, tendríamos que escribir un if por cada campo posible.
    """
    product = await get_product_by_id(db, product_id)
    if product is None:
        return None

    # Solo los campos que el cliente envió explícitamente
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product


# ============================================================
# DELETE — Soft delete
# ============================================================


async def delete_product(db: AsyncSession, product_id: int) -> Product | None:
    """
    Desactiva un producto (soft delete). No borra el registro de la BD.

    ¿Por qué soft delete y no DELETE real?
    - Historial: puedes saber que ese producto existió
    - Auditoría: si se vendió en el pasado, el registro histórico
      sigue intacto (importante para fases de Órdenes e Inventario)
    - Recuperación: si fue un error, se puede reactivar con un PUT

    En vez de borrar, solo marcamos is_active = False.
    get_products() ya filtra productos inactivos automáticamente.
    """
    product = await get_product_by_id(db, product_id)
    if product is None:
        return None

    product.is_active = False
    await db.commit()
    await db.refresh(product)
    return product
