# ============================================================
# BizCore — Schemas Pydantic para InventoryMovement
# ============================================================
#
# ANALOGÍA: si el modelo SQLAlchemy es la ficha interna del almacén
# con TODO el historial de un movimiento, estos schemas son los
# formularios que existen para interactuar con él:
#
#   InventoryMovementCreate   = formulario que llena el empleado
#   InventoryMovementResponse = copia del registro que devuelve el sistema
#
# ¿POR QUÉ NO HAY InventoryMovementUpdate?
# Los movimientos de inventario son INMUTABLES por diseño.
# Si alguien se equivocó, crea un movimiento corrector — no edita.
# Es el mismo principio que un extracto bancario: los bancos no
# modifican transacciones pasadas, crean asientos de corrección.
#
# ¿POR QUÉ NO ESTÁ `created_by_id` EN InventoryMovementCreate?
# Porque el sistema lo obtiene del JWT automáticamente.
# Permitir que el cliente envíe ese campo abriría una brecha:
# cualquiera podría atribuirle un movimiento a otro usuario.
# Misma decisión que tomamos con productos: el "quién" lo da el token,
# no el body del request.
#
# ============================================================

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InventoryMovementCreate(BaseModel):
    """
    Datos necesarios para registrar un movimiento de inventario.

    POST /api/v1/inventory

    Campos ausentes deliberadamente:
    - `id`: lo genera PostgreSQL (autoincrement)
    - `created_at`: lo genera PostgreSQL (server_default=func.now())
    - `created_by_id`: lo extrae el endpoint del JWT del usuario logueado
    """

    # product_id: qué producto se está moviendo.
    # gt=0: debe ser un entero positivo (los IDs empiezan en 1).
    product_id: int = Field(gt=0)

    # movement_type: Literal restringe los valores aceptados exactamente
    # a estas tres cadenas. Si el cliente envía "entrada" (minúscula)
    # o "VENTA" o cualquier otro valor, Pydantic rechaza el request
    # con un error 422 antes de que llegue a la base de datos.
    #
    # Literal["ENTRADA", "SALIDA", "AJUSTE"] es equivalente a decir:
    # "este campo solo puede contener uno de estos tres valores, nada más".
    movement_type: Literal["ENTRADA", "SALIDA", "AJUSTE"]

    # quantity: cantidad de unidades involucradas en el movimiento.
    # ge=1: "greater than or equal to 1" — siempre positivo, nunca cero.
    # La dirección la determina movement_type, no el signo de quantity.
    #   ENTRADA + quantity=50  → stock sube 50
    #   SALIDA  + quantity=3   → stock baja 3
    #   AJUSTE  + quantity=42  → stock queda en 42 (valor absoluto)
    quantity: int = Field(ge=1)

    # notes: contexto opcional del movimiento.
    # El empleado puede explicar el motivo: "compra proveedor XYZ",
    # "despacho factura #1234", "conteo físico mensual".
    # Si no se envía, queda como None en la BD (nullable).
    notes: str | None = Field(default=None, max_length=300)


class InventoryMovementResponse(BaseModel):
    """
    Datos del movimiento que la API devuelve al cliente.

    GET /api/v1/inventory
    GET /api/v1/inventory/{id}
    POST /api/v1/inventory  (respuesta después de crear)

    Incluye todos los campos: los que envió el cliente +
    los que generó el sistema (id, created_at, created_by_id).

    model_config = ConfigDict(from_attributes=True):
    Necesario para construir este schema desde un objeto SQLAlchemy.
    Sin esto, Pydantic esperaría un diccionario y fallaría al recibir
    una instancia de InventoryMovement.
    """

    id: int
    product_id: int
    movement_type: str
    quantity: int
    notes: str | None
    # created_by_id puede ser None si el usuario que creó el movimiento
    # fue eliminado posteriormente (ondelete="SET NULL" en el modelo).
    created_by_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryMovementPaginated(BaseModel):
    """
    Respuesta paginada para el historial de movimientos.

    GET /api/v1/inventory?page=1&page_size=10
    GET /api/v1/inventory?product_id=5&page=1

    ANALOGÍA: como el extracto bancario paginado — no traes todos los
    movimientos desde el inicio de los tiempos, traes una página y
    sabés cuántas páginas hay en total.
    """

    items: list[InventoryMovementResponse]  # movimientos de esta página
    total: int                              # total de movimientos en la BD
    page: int                              # página actual
    page_size: int                         # movimientos por página
    pages: int                             # total de páginas
