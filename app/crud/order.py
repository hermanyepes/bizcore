# ============================================================
# BizCore — CRUD: operaciones de base de datos para Order y OrderItem
# ============================================================
#
# ANALOGÍA: este archivo es el archivero de pedidos.
# Guarda carpetas (Orders) que contienen hojas (OrderItems).
# No decide si el pedido es válido, no calcula precios,
# no verifica si hay stock. Solo archiva, recupera y actualiza.
#
# DOS NOVEDADES EN ESTE CRUD:
#
# 1. selectinload — carga de relaciones en async
#    En SQLAlchemy async, los relationships NO se cargan solos.
#    Si haces select(Order), `order.items` llega vacío y falla al acceder.
#    selectinload(Order.items) le dice a SQLAlchemy: "cuando traigas
#    el Order, ejecuta inmediatamente un segundo SELECT para sus items".
#    Dos queries en secuencia, pero dentro de la misma operación async.
#
# 2. create_order recibe un objeto Order ya construido
#    En CRUDs anteriores, la función create_ recibía el schema (SupplierCreate)
#    y construía el objeto SQLAlchemy adentro.
#    Aquí es diferente: el servicio (services/order.py) construye el Order
#    completo — con sus items, precios copiados y subtotales calculados.
#    Este CRUD solo lo persiste. División de responsabilidades estricta.
#
# ¿POR QUÉ NO HAY create_order_item SEPARADO?
# Los OrderItems siempre nacen junto con su Order padre.
# El servicio los crea como una lista y los asigna a order.items.
# SQLAlchemy, gracias al cascade="all, delete-orphan" del relationship,
# los inserta automáticamente en la BD cuando se hace el commit del Order.
# No necesitamos una función CRUD separada para insertar ítems.
#
# ============================================================

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order
from app.schemas.order import OrderUpdate

# ============================================================
# GET — Consultas de lectura
# ============================================================


async def get_order_by_id(db: AsyncSession, order_id: int) -> Order | None:
    """
    Busca un pedido por su ID, incluyendo todos sus ítems.

    .options(selectinload(Order.items)):
    Ejecuta un segundo SELECT automáticamente para cargar los OrderItems.
    Sin esto, acceder a order.items en modo async lanzaría MissingGreenlet.

    Devuelve el objeto Order (con items cargados) si existe, None si no.
    """
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))  # carga los ítems del pedido
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def get_orders(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    supplier_id: int | None = None,
) -> tuple[list[Order], int]:
    """
    Devuelve una página de pedidos + el total de registros.

    ¿Para qué sirve `supplier_id` opcional?
    Permite filtrar pedidos por proveedor.
    Si se envía, devuelve solo los pedidos de ese proveedor.
    Si no se envía (None), devuelve todos los pedidos del sistema.

    Esto permite dos endpoints con la misma función:
      GET /api/v1/orders                    → todos los pedidos
      GET /api/v1/orders?supplier_id=3      → solo pedidos del proveedor 3

    Los pedidos se ordenan del más reciente al más antiguo (created_at DESC).

    ¿Por qué no filtramos por status?
    El administrador necesita ver todos los pedidos, incluyendo cancelados.
    Si en el futuro se necesita filtrar por status, se agrega el parámetro aquí.
    """
    # Construimos las queries base — reutilizamos el patrón de inventory y suppliers
    base_query = select(Order).options(selectinload(Order.items))
    count_query = select(func.count()).select_from(Order)

    # Si se especifica proveedor, filtramos en ambas queries
    if supplier_id is not None:
        base_query = base_query.where(Order.supplier_id == supplier_id)
        count_query = count_query.where(Order.supplier_id == supplier_id)

    # Query 1: pedidos de esta página, del más reciente al más antiguo
    orders_result = await db.execute(
        base_query
        .order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    orders = list(orders_result.scalars().all())

    # Query 2: total de pedidos (con o sin filtro de proveedor)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return orders, total


# ============================================================
# CREATE — Inserción
# ============================================================


async def create_order(db: AsyncSession, order: Order) -> Order:
    """
    Persiste en la BD un Order ya construido por el servicio.

    ¿Por qué recibe un objeto Order en vez de un schema OrderCreate?
    El servicio (services/order.py) es quien:
      - valida que el proveedor exista
      - valida que cada producto exista y esté activo
      - copia product.price → item.unit_price (snapshot)
      - calcula item.subtotal = quantity × unit_price
      - construye el objeto Order con sus OrderItems en order.items
    El CRUD no repite esa lógica. Recibe el trabajo hecho y lo persiste.

    ¿Cómo se insertan los OrderItems?
    El servicio asigna la lista a order.items antes de llamar aquí.
    Gracias al cascade="all, delete-orphan" del relationship en el modelo,
    SQLAlchemy inserta todos los OrderItems automáticamente en el commit.
    No hay que llamar db.add() por cada ítem — el cascado lo hace solo.

    ¿Por qué re-fetcheamos con get_order_by_id al final?
    Después de db.commit(), todos los atributos del objeto quedan "expirados"
    en SQLAlchemy — el motor sabe que la BD puede tener valores frescos.
    Si accedemos a order.items en ese estado, falla en async.
    Re-fetchear con selectinload garantiza que el objeto devuelto tiene
    todos sus atributos e ítems listos para serializar a JSON.
    """
    db.add(order)
    await db.commit()

    # Re-fetcheamos para devolver el objeto completo con items cargados
    created = await get_order_by_id(db, order.id)
    return created  # type: ignore[return-value]  # get_order_by_id devuelve Order aquí porque acabamos de crearlo


# ============================================================
# UPDATE — Actualización parcial (solo status y notes)
# ============================================================


async def update_order(
    db: AsyncSession,
    order_id: int,
    data: OrderUpdate,
) -> Order | None:
    """
    Actualiza solo los campos que el cliente envió (status y/o notes).

    ¿Por qué no se pueden actualizar los ítems?
    Los OrderItems son históricos — representan lo que se pidió en su momento.
    Cambiarlos equivaldría a falsificar el registro de compra.
    Si el pedido fue mal, se cancela y se crea uno nuevo.

    exclude_unset=True: si el cliente envía solo {"status": "COMPLETADO"},
    no tocamos notes. Solo actualizamos lo que llegó explícitamente.

    ¿Por qué re-fetcheamos con get_order_by_id al final?
    Mismo motivo que en create_order: después del commit los atributos
    expiran y necesitamos recargar con selectinload para tener items listos.
    """
    order = await get_order_by_id(db, order_id)
    if order is None:
        return None

    # Solo los campos que el cliente envió explícitamente
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)

    await db.commit()

    # Re-fetcheamos para devolver el objeto completo con items cargados
    return await get_order_by_id(db, order_id)


# ============================================================
# CANCEL — "Soft delete" vía status
# ============================================================


async def cancel_order(db: AsyncSession, order_id: int) -> Order | None:
    """
    Cancela un pedido cambiando su status a "CANCELADO".

    ¿Por qué no hay is_active=False como en los otros módulos?
    Los pedidos no desaparecen — siguen visibles en el historial
    de compras aunque estén cancelados. Un pedido cancelado es
    información de negocio valiosa: ¿cuántos pedidos se cancelaron
    este mes? ¿por qué proveedor?

    El "equivalente" de desactivar un pedido es ponerle status="CANCELADO".
    Sigue apareciendo en los listados, solo cambia su estado.

    ¿Por qué no hace hard delete (borrar la fila)?
    Dos razones:
    1. El historial de compras es auditable — no se puede borrar.
    2. OrderItems tienen ondelete="CASCADE": si borráramos el Order,
       todos sus items desaparecerían también. Eso es pérdida de historial.

    ¿Por qué re-fetcheamos con get_order_by_id al final?
    Mismo motivo que en update_order: recargamos con selectinload
    para tener los items listos después del commit.
    """
    order = await get_order_by_id(db, order_id)
    if order is None:
        return None

    order.status = "CANCELADO"
    await db.commit()

    # Re-fetcheamos para devolver el objeto completo con items cargados
    return await get_order_by_id(db, order_id)
