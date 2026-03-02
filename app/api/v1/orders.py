# ============================================================
# BizCore — Endpoints para Órdenes de Compra
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore para pedidos.
# Reciben la request HTTP, verifican el JWT, y coordinan con
# el servicio (para crear) o el CRUD (para leer/actualizar).
#
# FLUJO SEGÚN LA OPERACIÓN:
#
#   POST /orders/      → Mesero llama al gerente (service)
#                        El gerente coordina: valida proveedor,
#                        valida productos, congela precios,
#                        decrementa stock, guarda todo en un commit.
#
#   GET  /orders/      → Mesero va directo al bodeguero (crud)
#   GET  /orders/{id}  → Mesero va directo al bodeguero (crud)
#                        Solo lectura, sin lógica de negocio.
#
#   PUT  /orders/{id}  → Mesero va directo al bodeguero (crud)
#                        Solo cambia status y/o notes — sin cálculos.
#
#   DELETE /orders/{id} → Mesero va directo al bodeguero (crud)
#                         Solo cambia status a "CANCELADO".
#
# PERMISOS:
#   Crear pedidos       → cualquier usuario autenticado
#                         (los empleados también gestionan compras)
#   Ver pedidos         → cualquier usuario autenticado
#   Cambiar status      → solo Administrador
#   Cancelar            → solo Administrador
#
# ============================================================

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import order as order_crud
from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderPaginated,
    OrderResponse,
    OrderUpdate,
)
from app.services import order as order_service

# prefix="/orders": todas las rutas empiezan con /orders
# Combinado con el prefijo del router principal → /api/v1/orders
router = APIRouter(prefix="/orders", tags=["orders"])


# ============================================================
# GET /api/v1/orders — Listar pedidos (paginado)
# ============================================================
@router.get("/", response_model=OrderPaginated)
async def list_orders(
    page: int = 1,
    page_size: int = 10,
    supplier_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderPaginated:
    """
    Lista pedidos de compra con paginación.

    GET /api/v1/orders?page=1&page_size=10
    GET /api/v1/orders?supplier_id=3&page=1

    El parámetro `supplier_id` es opcional:
    - Sin él: devuelve todos los pedidos del sistema
    - Con él: devuelve solo los pedidos de ese proveedor

    Incluye pedidos en cualquier estado (PENDIENTE, COMPLETADO, CANCELADO).
    Los resultados vienen del más reciente al más antiguo.

    Cada pedido incluye su lista de ítems anidada (products, quantities,
    unit_price, subtotal).
    """
    skip = (page - 1) * page_size

    orders, total = await order_crud.get_orders(
        db,
        skip=skip,
        limit=page_size,
        supplier_id=supplier_id,
    )

    pages = math.ceil(total / page_size) if total > 0 else 0

    return OrderPaginated(
        items=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ============================================================
# GET /api/v1/orders/{order_id} — Obtener un pedido
# ============================================================
@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    """
    Devuelve los datos completos de un pedido, incluyendo todos sus ítems.

    GET /api/v1/orders/1

    La respuesta incluye:
    - Encabezado del pedido (proveedor, status, notas, fecha)
    - Lista de ítems con producto, cantidad, precio unitario y subtotal

    Si order_id no existe → 404.
    Si el token JWT es inválido o falta → 401.
    """
    order = await order_crud.get_order_by_id(db, order_id)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido con id '{order_id}' no encontrado",
        )

    return OrderResponse.model_validate(order)


# ============================================================
# POST /api/v1/orders — Crear pedido (cualquier usuario autenticado)
# ============================================================
@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    """
    Crea un pedido de compra con todos sus ítems.

    POST /api/v1/orders
    Body: OrderCreate (JSON)
    Requiere: JWT válido (cualquier rol)

    Ejemplo de body:
    {
        "supplier_id": 1,
        "notes": "Pedido mensual de harinas",
        "items": [
            {"product_id": 2, "quantity": 10},
            {"product_id": 5, "quantity": 3}
        ]
    }

    El sistema automáticamente:
    - Verifica que el proveedor exista y esté activo
    - Verifica que cada producto exista y esté activo
    - Copia el precio actual de cada producto (snapshot histórico)
    - Calcula el subtotal de cada ítem (quantity × unit_price)
    - Decrementa el stock de cada producto
    - Registra quién creó el pedido (del JWT, nunca del body)
    - Guarda todo en una sola transacción atómica

    Posibles errores:
      404 → proveedor o producto no existe
      400 → proveedor inactivo, producto inactivo, o stock insuficiente

    ¿Por qué llamamos al servicio y no al CRUD directamente?
    Crear un pedido coordina múltiples tablas, calcula precios y
    debe ocurrir como transacción atómica. Eso es lógica de negocio —
    responsabilidad del servicio, no del endpoint.

    ¿Cómo llega `created_by_id` al servicio?
    El endpoint extrae `current_user.document_id` del JWT.
    Nunca viene del body — el cliente no elige quién firma el pedido.
    """
    order = await order_service.create_order(
        db=db,
        data=data,
        created_by_id=current_user.document_id,
    )

    return OrderResponse.model_validate(order)


# ============================================================
# PUT /api/v1/orders/{order_id} — Actualizar pedido (solo Administrador)
# ============================================================
@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> OrderResponse:
    """
    Actualiza el status y/o las notas de un pedido.

    PUT /api/v1/orders/1
    Body: OrderUpdate (JSON)
    Requiere: JWT con rol Administrador

    Ejemplos de uso:
    - Completar un pedido:   {"status": "COMPLETADO"}
    - Agregar una nota:      {"notes": "Entregado el 2026-03-10"}
    - Ambas a la vez:        {"status": "COMPLETADO", "notes": "Entregado OK"}

    ¿Por qué solo el Administrador puede cambiar el status?
    Cambiar un pedido a COMPLETADO o CANCELADO es una decisión
    administrativa — confirma que se recibió la mercancía o que
    se revocó el pedido. No es una acción de cualquier empleado.

    ¿Por qué no se pueden actualizar los ítems?
    Los ítems son históricos. El precio y la cantidad quedan congelados
    al momento de crear el pedido. Modificarlos equivale a falsificar
    el registro de compra. Si el pedido fue mal → cancelar y crear uno nuevo.

    Si order_id no existe → 404.
    """
    order = await order_crud.update_order(db, order_id, data)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido con id '{order_id}' no encontrado",
        )

    return OrderResponse.model_validate(order)


# ============================================================
# DELETE /api/v1/orders/{order_id} — Cancelar pedido (solo Administrador)
# ============================================================
@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> OrderResponse:
    """
    Cancela un pedido cambiando su status a "CANCELADO".

    DELETE /api/v1/orders/1
    Requiere: JWT con rol Administrador

    ¿Por qué no borramos la fila de la BD?
    Los pedidos de compra son registros auditables. Un pedido
    cancelado sigue siendo información de negocio valiosa:
    ¿cuántos pedidos se cancelaron? ¿con qué proveedor?
    El historial debe conservarse intacto.

    ¿Se restaura el stock al cancelar?
    En esta versión, no. Si un pedido se cancela, el administrador
    debe registrar manualmente una ENTRADA de inventario para
    restablecer el stock de los productos afectados. Esta es una
    decisión de alcance — en sistemas más complejos, la cancelación
    revertiría el stock automáticamente.

    La respuesta devuelve el pedido con status="CANCELADO",
    confirmando visualmente que fue cancelado.

    Si order_id no existe → 404.
    """
    order = await order_crud.cancel_order(db, order_id)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido con id '{order_id}' no encontrado",
        )

    return OrderResponse.model_validate(order)
