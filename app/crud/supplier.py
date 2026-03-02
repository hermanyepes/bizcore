# ============================================================
# BizCore — CRUD: operaciones de base de datos para Supplier
# ============================================================
#
# ANALOGÍA: este archivo es el bodeguero de la libreta de proveedores.
# Solo habla con PostgreSQL. No sabe si el usuario tiene sesión,
# no valida permisos, no toma decisiones de negocio.
# Solo recibe instrucciones y ejecuta: guarda, trae, actualiza.
#
# Cada función recibe `db` (la sesión de BD) como primer parámetro.
# FastAPI la inyecta automáticamente vía Depends(get_db).
#
# ============================================================

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate

# ============================================================
# GET — Consultas de lectura
# ============================================================


async def get_supplier_by_id(db: AsyncSession, supplier_id: int) -> Supplier | None:
    """
    Busca un proveedor por su id numérico.

    Devuelve el objeto Supplier si existe, None si no.
    El endpoint usa este resultado para devolver 404 si es None.
    """
    result = await db.execute(
        select(Supplier).where(Supplier.id == supplier_id)
    )
    return result.scalar_one_or_none()


async def get_supplier_by_name(db: AsyncSession, name: str) -> Supplier | None:
    """
    Busca un proveedor por su nombre exacto.

    ¿Para qué sirve?
    Para verificar duplicados antes de crear o renombrar un proveedor.
    Si ya existe uno con ese nombre, el endpoint devuelve 409 con un
    mensaje claro, en vez de dejar que PostgreSQL lance un error
    críptico de constraint violation.
    """
    result = await db.execute(
        select(Supplier).where(Supplier.name == name)
    )
    return result.scalar_one_or_none()


async def get_supplier_by_email(db: AsyncSession, email: str) -> Supplier | None:
    """
    Busca un proveedor por su email de contacto.

    ¿Para qué sirve?
    Igual que get_supplier_by_name: detectar duplicados de email
    antes de que PostgreSQL los rechace con un error de constraint.
    El endpoint usa esto para devolver 409 con un mensaje legible.
    """
    result = await db.execute(
        select(Supplier).where(Supplier.contact_email == email)
    )
    return result.scalar_one_or_none()


async def get_suppliers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
) -> tuple[list[Supplier], int]:
    """
    Devuelve una página de proveedores activos + el total de registros activos.

    ¿Por qué skip y limit en vez de page y page_size?
    skip y limit son los términos nativos de SQL (OFFSET y LIMIT).
    La conversión page → skip la hace el endpoint:
        skip = (page - 1) * page_size

    ¿Por qué filtramos is_active=True?
    Los proveedores desactivados (soft delete) no deben aparecer
    en el listado. Siguen en la BD, pero son invisibles para la API.

    ¿Por qué dos queries?
    Son dos preguntas distintas:
    1. "Dame los proveedores de esta página" → select con limit/offset
    2. "¿Cuántos proveedores activos hay en total?" → select count(*)
    Sin el total no podemos calcular cuántas páginas existen.
    """
    # Query 1: los proveedores activos de esta página
    suppliers_result = await db.execute(
        select(Supplier)
        .where(Supplier.is_active == True)  # noqa: E712
        .offset(skip)
        .limit(limit)
    )
    suppliers = list(suppliers_result.scalars().all())

    # Query 2: el total de proveedores activos en la BD
    count_result = await db.execute(
        select(func.count())
        .select_from(Supplier)
        .where(Supplier.is_active == True)  # noqa: E712
    )
    total = count_result.scalar_one()

    return suppliers, total


# ============================================================
# CREATE — Inserción
# ============================================================


async def create_supplier(db: AsyncSession, data: SupplierCreate) -> Supplier:
    """
    Crea un nuevo proveedor en la BD.

    Flujo:
    1. Construimos el objeto Supplier con los datos del schema
    2. db.add() lo agrega a la sesión (en memoria, aún no en la BD)
    3. db.commit() ejecuta el INSERT en PostgreSQL
    4. db.refresh() recarga el objeto para obtener los valores
       generados por el servidor (id, created_at)

    ¿Por qué db.refresh()?
    Antes del commit, `supplier.id` es None. PostgreSQL aún no
    asignó el número autoincremental. Refresh lo trae desde la BD.
    """
    supplier = Supplier(
        name=data.name,
        contact_email=data.contact_email,
        phone=data.phone,
        address=data.address,
        # id y created_at los genera PostgreSQL automáticamente
        # is_active empieza en True por el default del modelo
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


# ============================================================
# UPDATE — Actualización parcial
# ============================================================


async def update_supplier(
    db: AsyncSession,
    supplier_id: int,
    data: SupplierUpdate,
) -> Supplier | None:
    """
    Actualiza solo los campos que el cliente envió.

    exclude_unset=True: filtra únicamente los campos que llegaron
    en el request. Si el cliente envía solo {"phone": "310 555 1234"},
    no sobreescribimos name, email ni address con None.

    setattr(supplier, field, value): asigna dinámicamente el valor
    al atributo del objeto. Es equivalente a supplier.phone = "310..."
    pero funciona sin saber de antemano qué campo es.
    """
    supplier = await get_supplier_by_id(db, supplier_id)
    if supplier is None:
        return None

    # Solo los campos que el cliente envió explícitamente
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(supplier, field, value)

    await db.commit()
    await db.refresh(supplier)
    return supplier


# ============================================================
# DELETE — Soft delete
# ============================================================


async def delete_supplier(db: AsyncSession, supplier_id: int) -> Supplier | None:
    """
    Desactiva un proveedor (soft delete). No borra el registro de la BD.

    ¿Por qué soft delete?
    En Phase 5, los pedidos (Orders) van a referenciar proveedores.
    Si borráramos la fila, esos pedidos históricos quedarían rotos.
    Desactivar conserva el historial intacto.

    get_suppliers() filtra is_active=True, así que el proveedor
    desactivado desaparece del listado pero sigue en la BD.
    """
    supplier = await get_supplier_by_id(db, supplier_id)
    if supplier is None:
        return None

    supplier.is_active = False
    await db.commit()
    await db.refresh(supplier)
    return supplier
