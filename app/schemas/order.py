# ============================================================
# BizCore — Schemas Pydantic para Order y OrderItem
# ============================================================
#
# ANALOGÍA: cada schema es un formulario distinto según la situación.
#
#   OrderItemCreate    = una línea del formulario de pedido:
#                        "qué producto y cuántos" — el precio lo pone el sistema
#   OrderCreate        = el formulario completo del pedido:
#                        a quién le compramos + lista de líneas
#
#   OrderUpdate        = formulario de cambio de estado:
#                        solo status y notas — los ítems son inmutables
#
#   OrderItemResponse  = una línea de la factura devuelta:
#                        incluye precio y subtotal calculados
#   OrderResponse      = la factura completa devuelta:
#                        encabezado + lista de líneas anidada
#   OrderPaginated     = listado paginado de pedidos
#
# LA NOVEDAD DE ESTE ARCHIVO — Schemas anidados:
# OrderResponse contiene `items: list[OrderItemResponse]`.
# Pydantic puede anidar un schema dentro de otro.
# Cuando FastAPI devuelve un objeto SQLAlchemy `Order`,
# Pydantic usa `order.items` (el relationship()) y convierte
# cada `OrderItem` automáticamente en un `OrderItemResponse`.
# Funciona porque ambos schemas tienen `from_attributes=True`.
#
# ============================================================

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Schemas de INPUT — lo que el cliente envía
# ============================================================


class OrderItemCreate(BaseModel):
    """
    Una línea dentro del formulario de creación de pedido.

    El cliente especifica QUÉ producto y CUÁNTOS.
    El sistema busca el precio actual del producto y lo congela.

    Campos ausentes deliberadamente:
    - `unit_price`: lo copia el servicio desde product.price (snapshot)
    - `subtotal`: lo calcula el servicio (quantity × unit_price)
    - `order_id`: lo asigna el servicio después de crear el Order padre
    """

    # product_id: qué producto entra en este ítem del pedido.
    # gt=0: los IDs empiezan en 1, nunca puede ser 0 o negativo.
    product_id: int = Field(gt=0)

    # quantity: cuántas unidades de ese producto se piden.
    # ge=1: no tiene sentido pedir cero o menos de algo.
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    """
    Datos necesarios para crear un pedido nuevo.

    POST /api/v1/orders

    Un pedido tiene un proveedor, notas opcionales,
    y al menos una línea de ítem. Sin ítems no hay pedido.

    Campos ausentes deliberadamente:
    - `id`: lo genera PostgreSQL (autoincrement)
    - `status`: siempre nace como "PENDIENTE" (default del modelo)
    - `created_at`: lo genera PostgreSQL (server_default=func.now())
    - `created_by_id`: lo extrae el endpoint del JWT del usuario logueado
    """

    # supplier_id: a qué proveedor le estamos haciendo el pedido.
    # gt=0: IDs válidos empiezan en 1.
    supplier_id: int = Field(gt=0)

    # notes: contexto libre del pedido.
    # "compra mensual de harina", "pedido urgente por faltante", etc.
    notes: str | None = Field(default=None, max_length=300)

    # items: lista de líneas del pedido.
    # min_length=1: un pedido sin ítems no tiene sentido de negocio —
    # no puedes hacer un pedido de "nada". Pydantic rechaza la lista
    # vacía antes de que llegue al servicio.
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderUpdate(BaseModel):
    """
    Datos que se pueden actualizar en un pedido existente.

    PUT /api/v1/orders/{id}

    ¿POR QUÉ SOLO STATUS Y NOTES?
    Los ítems son inmutables una vez creados. Si ya se registró que
    se pidieron 5 kilos de harina a $80.000, ese dato es histórico.
    Modificarlo sería falsificar el historial.

    Si el pedido fue mal, se cancela (status="CANCELADO") y se crea
    uno nuevo. No se editan las líneas.

    ¿POR QUÉ NO INCLUIMOS `is_active`?
    Los pedidos no tienen soft delete con is_active.
    El "equivalente" de desactivar un pedido es ponerle status="CANCELADO".
    """

    # status: el nuevo estado del pedido.
    # Literal: solo estos tres valores son válidos.
    # | None: el campo es opcional — si no se envía, no se cambia.
    status: Literal["PENDIENTE", "COMPLETADO", "CANCELADO"] | None = None

    # notes: actualizar el comentario del pedido.
    # | None con default=None: si no se envía, no se cambia.
    # Si se envía explícitamente notes=None, borra las notas existentes.
    notes: str | None = Field(default=None, max_length=300)


# ============================================================
# Schemas de OUTPUT — lo que la API devuelve
# ============================================================


class OrderItemResponse(BaseModel):
    """
    Una línea de la factura devuelta por la API.

    Incluye los campos calculados por el sistema:
    unit_price (snapshot del precio) y subtotal (calculado al crear).

    from_attributes=True: necesario porque construimos este schema
    desde un objeto SQLAlchemy `OrderItem`, no desde un diccionario.
    """

    id: int
    order_id: int
    product_id: int
    quantity: int
    unit_price: int   # precio congelado al momento del pedido
    subtotal: int     # quantity × unit_price, guardado en la BD

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    """
    La factura completa devuelta por la API.

    GET /api/v1/orders
    GET /api/v1/orders/{id}
    POST /api/v1/orders  (respuesta después de crear)

    ¿CÓMO FUNCIONA EL CAMPO `items` ANIDADO?
    1. El endpoint devuelve un objeto SQLAlchemy `Order`.
    2. Pydantic lee `order.items` gracias al relationship().
    3. Como `items` está tipado como `list[OrderItemResponse]`,
       Pydantic convierte cada `OrderItem` usando `OrderItemResponse`.
    4. Todo esto funciona porque ambos schemas tienen from_attributes=True.

    El resultado: una sola respuesta JSON con el encabezado y todos
    sus ítems anidados, sin escribir ningún JOIN manualmente.
    """

    id: int
    supplier_id: int
    created_by_id: str | None  # None si el usuario fue borrado (SET NULL)
    status: str
    notes: str | None
    created_at: datetime

    # Lista de ítems anidada — la novedad visual de este schema.
    # Pydantic la construye automáticamente desde order.items.
    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)


class OrderPaginated(BaseModel):
    """
    Respuesta paginada para el listado de pedidos.

    GET /api/v1/orders?page=1&page_size=10

    Mismo patrón que los demás módulos paginados.
    Cada elemento del listado incluye sus ítems anidados.
    """

    items: list[OrderResponse]  # pedidos de esta página
    total: int                  # total de pedidos en la BD
    page: int                   # página actual
    page_size: int              # pedidos por página
    pages: int                  # total de páginas
