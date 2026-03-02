# ============================================================
# BizCore — Servicio: lógica de negocio para Orders
# ============================================================
#
# ANALOGÍA: este archivo es el gerente de compras.
# Cuando llega una orden de pedido, el gerente no la ejecuta ciegamente.
# Primero verifica: ¿el proveedor existe? ¿tenemos los productos?
# ¿hay suficiente stock de cada uno? Solo si todo está bien, arma
# el pedido, congela los precios, calcula los totales, y lo registra.
#
# ¿POR QUÉ EXISTE ESTA CAPA?
# Crear un pedido no es una operación simple de BD:
#   - Hay que validar el proveedor (1 consulta)
#   - Hay que validar cada producto (N consultas)
#   - Hay que copiar el precio actual de cada producto (snapshot)
#   - Hay que calcular el subtotal de cada ítem
#   - Hay que decrementar el stock de cada producto
#   - Todo debe ocurrir o nada debe ocurrir (transacción atómica)
# Esa lógica no le corresponde al CRUD (bodeguero) ni al endpoint (mesero).
#
# LA TRANSACCIÓN ATÓMICA — la novedad central de este servicio:
#
# En Phase 3 (inventario), usamos dos commits separados:
#   commit 1 → insertar el movimiento
#   commit 2 → actualizar el stock
# Era un tradeoff aceptable para un módulo simple.
#
# En Phase 5 necesitamos más rigor. La receta:
#   1. Hacer TODA la preparación en memoria (sin commit)
#   2. Un SOLO db.add(order) + await db.commit() al final
#   3. SQLAlchemy, gracias al cascade="all, delete-orphan", inserta
#      el Order y todos sus OrderItems en ese único commit
#   4. Los cambios a product.stock también van en ese mismo commit
#
# Si algo falla (excepción, BD caída) antes del commit:
#   → nada se guarda. La BD queda intacta. Cero datos corruptos.
# Si el commit mismo falla:
#   → PostgreSQL revierte todo automáticamente (transacción ACID).
#
# ANALOGÍA de la transacción:
# Es como llenar un cheque bancario. Lo llenas completo en papel
# (en memoria), y solo cuando estás seguro de todo lo entregas
# (commit). Si te equivocas llenándolo, lo rompes y empiezas de nuevo.
# No existe "entregar el cheque a medias".
#
# ============================================================

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.order import get_order_by_id
from app.crud.product import get_product_by_id
from app.crud.supplier import get_supplier_by_id
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate


async def create_order(
    db: AsyncSession,
    data: OrderCreate,
    created_by_id: str,
) -> Order:
    """
    Crea un pedido de compra completo de forma atómica.

    Parámetros:
    - db: sesión de BD inyectada por FastAPI
    - data: datos del pedido validados por Pydantic (viene del endpoint)
    - created_by_id: document_id del usuario logueado (viene del JWT)

    Pasos internos:
    1. Validar que el proveedor existe y está activo
    2. Por cada ítem: validar producto, verificar stock, copiar precio
    3. Construir los objetos Order y OrderItem en memoria
    4. Marcar los decrementos de stock en memoria
    5. Un solo commit → todo se guarda o todo se revierte
    6. Re-fetchear con items cargados y devolver
    """

    # ----------------------------------------------------------
    # Paso 1: validar el proveedor
    #
    # ¿Por qué validar is_active?
    # No tiene sentido hacer un pedido a un proveedor desactivado.
    # Un proveedor desactivado puede ser uno con el que ya no
    # trabajamos, o uno que registramos por error.
    # ----------------------------------------------------------
    supplier = await get_supplier_by_id(db, data.supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Proveedor no encontrado",
        )

    if not supplier.is_active:
        raise HTTPException(
            status_code=400,
            detail="No se puede crear un pedido para un proveedor inactivo",
        )

    # ----------------------------------------------------------
    # Paso 2: validar cada producto y preparar los ítems
    #
    # Recorremos todos los ítems ANTES de crear cualquier objeto.
    # Si el producto 3 de una lista de 5 es inválido, queremos
    # rechazar TODO el pedido, no crear 2 ítems y fallar en el 3ro.
    #
    # Guardamos en `prepared_items` la información necesaria para
    # construir los objetos OrderItem sin volver a consultar la BD.
    # Cada elemento: (datos del ítem del schema, precio del producto,
    #                  subtotal calculado, objeto product en memoria)
    # ----------------------------------------------------------
    prepared_items = []

    for item_data in data.items:
        product = await get_product_by_id(db, item_data.product_id)

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Producto con id {item_data.product_id} no encontrado",
            )

        if not product.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"El producto '{product.name}' está inactivo y no puede pedirse",
            )

        if product.stock < item_data.quantity:
            # 400: la petición es válida en formato pero inválida dado
            # el estado actual del sistema (stock insuficiente).
            # Incluimos los números para que el mensaje sea útil.
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Stock insuficiente para '{product.name}'. "
                    f"Disponible: {product.stock}, solicitado: {item_data.quantity}"
                ),
            )

        # Snapshot del precio: tomamos product.price en este momento.
        # Si mañana el precio cambia, este pedido histórico no se ve afectado.
        unit_price = product.price
        subtotal = item_data.quantity * unit_price

        prepared_items.append((item_data, unit_price, subtotal, product))

    # ----------------------------------------------------------
    # Paso 3: construir los objetos en memoria (sin commit todavía)
    #
    # Creamos primero los OrderItem, luego el Order.
    # El Order recibe la lista de ítems en su constructor gracias
    # al relationship — SQLAlchemy los enlaza automáticamente.
    # Ninguno de estos objetos está en la BD aún.
    # ----------------------------------------------------------
    order_items = [
        OrderItem(
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            unit_price=unit_price,
            subtotal=subtotal,
            # order_id lo asigna SQLAlchemy automáticamente al hacer
            # el commit — sabe que estos ítems pertenecen al Order padre
        )
        for item_data, unit_price, subtotal, _ in prepared_items
    ]

    order = Order(
        supplier_id=data.supplier_id,
        created_by_id=created_by_id,
        notes=data.notes,
        items=order_items,
        # status="PENDIENTE" por el default del modelo
        # created_at lo genera PostgreSQL con server_default=func.now()
    )

    # ----------------------------------------------------------
    # Paso 4: decrementar el stock de cada producto en memoria
    #
    # Modificamos los atributos de los objetos product que ya están
    # en la sesión de SQLAlchemy (los cargamos en el paso 2).
    # SQLAlchemy rastrea estos cambios y los incluirá en el commit.
    # El stock NO se actualiza en la BD todavía — solo en memoria.
    # ----------------------------------------------------------
    for item_data, _, _, product in prepared_items:
        product.stock -= item_data.quantity

    # ----------------------------------------------------------
    # Paso 5: UN SOLO commit — la transacción atómica
    #
    # db.add(order): registra el Order en la sesión de SQLAlchemy.
    # El cascade="all, delete-orphan" del relationship hace que
    # los OrderItems también se registren automáticamente — no
    # necesitamos db.add() por cada ítem.
    #
    # await db.commit(): envía TODO a PostgreSQL en una sola
    # transacción. PostgreSQL garantiza ACID: o se guardan
    # el Order, sus N OrderItems y los M cambios de stock juntos,
    # o no se guarda NADA si algo falla.
    #
    # Esta es la diferencia clave con Phase 3:
    # Phase 3: dos commits separados (tradeoff documentado)
    # Phase 5: un solo commit (transacción verdaderamente atómica)
    # ----------------------------------------------------------
    db.add(order)
    await db.commit()

    # ----------------------------------------------------------
    # Paso 6: re-fetchear con items cargados y devolver
    #
    # Después del commit, los atributos del objeto `order` expiran
    # en SQLAlchemy — el motor sabe que la BD puede tener valores
    # frescos (id, created_at, order_id de cada ítem, etc.).
    # get_order_by_id usa selectinload para devolver el Order completo
    # con todos sus ítems listos para serializar a JSON.
    # ----------------------------------------------------------
    return await get_order_by_id(db, order.id)  # type: ignore[return-value]
