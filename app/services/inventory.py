# ============================================================
# BizCore — Servicio: lógica de negocio para Inventario
# ============================================================
#
# ANALOGÍA: este archivo es el gerente del almacén.
# A diferencia del CRUD (que solo ejecuta sin preguntar) y del
# endpoint (que solo recibe al cliente y verifica el JWT), el
# servicio DECIDE: valida reglas de negocio, calcula resultados
# y coordina múltiples operaciones de BD.
#
# ¿POR QUÉ EXISTE ESTA CAPA Y NO ESTÁ TODO EN EL ENDPOINT?
# El endpoint tiene una responsabilidad: hablar con el cliente HTTP.
# Si metemos lógica de negocio ahí, el endpoint crece y se vuelve
# difícil de testear y de reutilizar.
# El servicio es fácil de llamar desde distintos lugares sin duplicar
# la lógica (ej: desde un endpoint de "recibir orden" en el futuro).
#
# ¿POR QUÉ NO ESTÁ EN EL CRUD?
# El CRUD no tiene opinión: ejecuta lo que le piden.
# Preguntas como "¿hay suficiente stock?" o "¿el producto está activo?"
# son reglas del negocio — no le corresponden al bodeguero.
#
# ============================================================

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.inventory_movement import create_movement
from app.crud.product import get_product_by_id
from app.models.inventory_movement import InventoryMovement
from app.schemas.inventory_movement import InventoryMovementCreate


async def register_movement(
    db: AsyncSession,
    data: InventoryMovementCreate,
    created_by_id: str,
) -> InventoryMovement:
    """
    Registra un movimiento de inventario y actualiza el stock del producto.

    Este es el único punto del sistema donde se puede modificar el stock.
    Centralizar aquí garantiza que SIEMPRE quede un registro del movimiento
    antes de tocar el stock — nunca se actualiza stock sin dejar rastro.

    Pasos:
    1. Verificar que el producto existe y está activo
    2. Calcular el nuevo stock según el tipo de movimiento
    3. Validar que el resultado no sea negativo (solo para SALIDA)
    4. Crear el registro del movimiento en inventory_movements
    5. Actualizar product.stock con el nuevo valor

    Parámetros:
    - db: sesión de BD inyectada por FastAPI
    - data: datos del movimiento validados por Pydantic (viene del endpoint)
    - created_by_id: document_id del usuario logueado (viene del JWT)
    """

    # ----------------------------------------------------------
    # Paso 1: verificar que el producto existe y está activo
    #
    # ¿Por qué verificar is_active?
    # Un producto desactivado (soft delete) no debería recibir
    # movimientos de inventario. No tiene sentido registrar stock
    # para algo que el negocio considera fuera de catálogo.
    # ----------------------------------------------------------
    product = await get_product_by_id(db, data.product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado",
        )

    if not product.is_active:
        raise HTTPException(
            status_code=400,
            detail="No se pueden registrar movimientos para un producto inactivo",
        )

    # ----------------------------------------------------------
    # Paso 2 + 3: calcular el nuevo stock y validar el resultado
    #
    # Cada tipo de movimiento tiene una lógica diferente:
    #
    #   ENTRADA: se suma la cantidad al stock actual
    #     stock=10, quantity=50 → nuevo stock=60
    #
    #   SALIDA: se resta la cantidad del stock actual
    #     stock=10, quantity=3  → nuevo stock=7
    #     stock=10, quantity=15 → RECHAZADO (no hay suficiente)
    #
    #   AJUSTE: se fija el stock al valor exacto indicado
    #     stock=10, quantity=42 → nuevo stock=42 (conteo físico)
    #     Útil cuando el conteo real no coincide con el sistema.
    #
    # ¿Por qué solo SALIDA puede rechazarse?
    # ENTRADA siempre suma (nunca negativo).
    # AJUSTE fija un valor absoluto (siempre >= 1 por el schema).
    # Solo SALIDA puede intentar restar más de lo disponible.
    # ----------------------------------------------------------
    if data.movement_type == "ENTRADA":
        new_stock = product.stock + data.quantity

    elif data.movement_type == "SALIDA":
        new_stock = product.stock - data.quantity

        if new_stock < 0:
            # 400 Bad Request: la petición es válida en formato pero
            # inválida dado el estado actual del sistema (stock insuficiente).
            # El mensaje incluye los números para que el cliente sepa
            # cuánto hay y cuánto pidió — más útil que "error genérico".
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Stock insuficiente. "
                    f"Disponible: {product.stock}, solicitado: {data.quantity}"
                ),
            )

    else:  # AJUSTE
        new_stock = data.quantity

    # ----------------------------------------------------------
    # Paso 4: crear el registro del movimiento
    #
    # El CRUD inserta la fila en inventory_movements y hace commit.
    # A partir de este punto queda evidencia del movimiento en la BD.
    # ----------------------------------------------------------
    movement = await create_movement(db, data, created_by_id)

    # ----------------------------------------------------------
    # Paso 5: actualizar el stock del producto
    #
    # El objeto `product` ya está en la sesión de SQLAlchemy (lo
    # cargamos en el Paso 1). Solo necesitamos cambiar el atributo
    # y hacer commit — SQLAlchemy sabe qué fila actualizar.
    #
    # Nota técnica: los pasos 4 y 5 son dos commits separados.
    # En un sistema financiero necesitaríamos una sola transacción
    # atómica (o revertir ambas si una falla). Para el alcance de
    # este proyecto, la ventana de fallo entre los dos commits es
    # extremadamente pequeña y aceptable.
    # ----------------------------------------------------------
    product.stock = new_stock
    await db.commit()
    await db.refresh(product)

    return movement
