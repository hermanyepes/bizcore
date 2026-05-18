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
# PERMISOS (ver docs/roles/matriz-permisos.md sección 2.5):
#   Todos los endpoints → require_employee (cualquier usuario autenticado)
#
# NOTA sobre row-level security:
#   La matriz define restricciones más finas por rol (el Empleado
#   solo ve sus propias órdenes, solo puede cancelar las suyas, etc.)
#   Esas restricciones se implementan en el SERVICE en la Sesión 5
#   del roadmap. Por ahora el endpoint-level permite acceso a
#   cualquier usuario autenticado.
#
# ============================================================

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.crud import order as order_crud
from app.dependencies import get_db, require_employee
from app.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderPaginated,
    OrderResponse,
    OrderStatusUpdate,
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
    page: int = Query(default=1, ge=1),  # mínimo página 1
    page_size: int = Query(default=10, ge=1, le=100),  # entre 1 y 100 registros
    supplier_id: int | None = None,
    status: str | None = Query(default=None),  # 'PENDIENTE'/'RECIBIDO'/'CANCELADO'
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee),  # cualquier usuario autenticado
) -> OrderPaginated:
    """
    Lista pedidos de compra con paginación y filtros opcionales.

    Row-level security (HU-043):
    - Empleado    → solo sus propias órdenes (WHERE created_by_id = document_id)
    - Supervisor+ → todas las órdenes sin restricción

    GET /api/v1/orders?page=1&page_size=10
    GET /api/v1/orders?status=PENDIENTE
    GET /api/v1/orders?supplier_id=3&status=APROBADA
    Requiere: JWT válido (cualquier rol)
    """
    skip = (page - 1) * page_size

    orders, total = await order_service.list_orders_for_user(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=page_size,
        supplier_id=supplier_id,
        status=status,
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
    current_user: User = Depends(require_employee),  # cualquier usuario autenticado
) -> OrderResponse:
    """
    Devuelve los datos completos de un pedido, incluyendo todos sus ítems.

    Row-level security (HU-043):
    - Empleado que intenta ver una orden ajena → 403.
    - Supervisor+ puede ver cualquier orden.

    GET /api/v1/orders/1
    Requiere: JWT válido (cualquier rol)

    Si order_id no existe → 404.
    Si el Empleado intenta ver una orden ajena → 403.
    """
    order = await order_crud.get_order_by_id(db, order_id)

    if order is None:
        raise NotFoundError("Pedido", order_id)

    if current_user.role == UserRole.EMPLOYEE:
        if order.created_by_id != current_user.document_id:
            raise PermissionDeniedError("No tienes acceso a esta orden")

    return OrderResponse.model_validate(order)


# ============================================================
# POST /api/v1/orders — Crear pedido (cualquier usuario autenticado)
# ============================================================
@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee),  # cualquier usuario autenticado
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
# PUT /api/v1/orders/{order_id}/status — Cambiar estado (máquina de estados)
# ============================================================
@router.put("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee),
) -> OrderResponse:
    """
    Cambia el estado de una orden aplicando la máquina de estados completa.

    PUT /api/v1/orders/1/status
    Body: {"status": "APROBADA"} | {"status": "CANCELADA", "cancel_reason": "..."}

    Transiciones válidas (ver docs/diagramas/flujo-orden.md):
      PENDIENTE → APROBADA   (Supervisor / Admin / Superadmin)
      PENDIENTE → CANCELADA  (cualquier autenticado — row-level en service)
      APROBADA  → ENTREGADA  (Supervisor / Admin / Superadmin)
      APROBADA  → CANCELADA  (Supervisor / Admin / Superadmin)

    Restricciones de rol (HU-043, HU-046):
    - Empleado: solo PENDIENTE → CANCELADA sobre su propia orden con cancel_reason.
    - Cualquier otra transición por parte del Empleado → 403.
    - Orden ajena para el Empleado → 403.

    Si order_id no existe → 404.
    """
    order = await order_service.update_status(
        db=db,
        order_id=order_id,
        new_status=data.status,
        current_user=current_user,
        cancel_reason=data.cancel_reason,
    )
    return OrderResponse.model_validate(order)


# ============================================================
# PUT /api/v1/orders/{order_id} — Actualizar pedido (legacy)
# ============================================================
@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee),  # cualquier autenticado — row-level en Sesión 5
) -> OrderResponse:
    """
    Actualiza el status y/o las notas de un pedido.

    PUT /api/v1/orders/1
    Body: OrderUpdate (JSON)
    Requiere: JWT válido (cualquier rol)

    Nota: las restricciones de row-level (el Empleado solo puede
    actualizar sus propias órdenes en estado PENDIENTE) se implementan
    en el servicio en la Sesión 5 del roadmap.

    ¿Por qué no se pueden actualizar los ítems?
    Los ítems son históricos. El precio y la cantidad quedan congelados
    al momento de crear el pedido. Modificarlos equivale a falsificar
    el registro de compra. Si el pedido fue mal → cancelar y crear uno nuevo.

    Si order_id no existe → 404.
    """
    order = await order_crud.update_order(db, order_id, data)

    if order is None:
        raise NotFoundError("Pedido", order_id)

    return OrderResponse.model_validate(order)


# ============================================================
# DELETE /api/v1/orders/{order_id} — Cancelar pedido
# ============================================================
@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_employee),  # cualquier autenticado — row-level en Sesión 5
) -> OrderResponse:
    """
    Cancela un pedido cambiando su status a "CANCELADO".

    DELETE /api/v1/orders/1
    Requiere: JWT válido (cualquier rol)

    Nota: las restricciones de row-level (el Empleado solo puede
    cancelar sus propias órdenes) se implementan en el servicio
    en la Sesión 5 del roadmap.

    ¿Por qué no borramos la fila de la BD?
    Los pedidos de compra son registros auditables. Un pedido
    cancelado sigue siendo información de negocio valiosa:
    ¿cuántos pedidos se cancelaron? ¿con qué proveedor?
    El historial debe conservarse intacto.

    La respuesta devuelve el pedido con status="CANCELADO",
    confirmando visualmente que fue cancelado.

    Si order_id no existe → 404.
    """
    order = await order_crud.cancel_order(db, order_id)

    if order is None:
        raise NotFoundError("Pedido", order_id)

    return OrderResponse.model_validate(order)
