# ============================================================
# BizCore — Endpoints para Inventario
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore para inventario.
# Su trabajo es el de siempre: recibir el pedido HTTP, verificar
# el JWT, y devolver la respuesta al cliente.
#
# DIFERENCIA CLAVE respecto a products:
# Para el POST, el mesero NO va directo al bodeguero (CRUD).
# Va primero al gerente (services/inventory.py) porque registrar
# un movimiento requiere lógica de negocio: calcular el nuevo
# stock, validar que no quede negativo, coordinar dos operaciones.
#
# Para los GET, sí va directo al bodeguero — solo lectura, sin
# lógica de negocio, sin efectos secundarios.
#
# FLUJO DEL POST:
#   1. FastAPI recibe POST /api/v1/inventory
#   2. Ejecuta get_db() y get_current_user() vía Depends
#   3. get_current_user() verifica JWT → devuelve el usuario logueado
#   4. El endpoint extrae current_user.document_id (el "quién")
#   5. Llama al servicio pasando datos + document_id
#   6. El servicio valida, calcula y coordina CRUD + stock
#   7. FastAPI serializa la respuesta con response_model
#
# ¿POR QUÉ CUALQUIER USUARIO AUTENTICADO PUEDE REGISTRAR MOVIMIENTOS?
# En una bodega real, los empleados son quienes reciben mercancía
# (ENTRADA) y despachan pedidos (SALIDA). No tiene sentido restringir
# esto solo al Administrador — ellos también trabajan con el inventario.
#
# ============================================================

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import inventory_movement as inventory_crud
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.inventory_movement import (
    InventoryMovementCreate,
    InventoryMovementPaginated,
    InventoryMovementResponse,
)
from app.services import inventory as inventory_service

# prefix="/inventory": todas las rutas empiezan con /inventory
# Combinado con el prefijo del router principal → /api/v1/inventory
router = APIRouter(prefix="/inventory", tags=["inventory"])


# ============================================================
# GET /api/v1/inventory — Listar movimientos (paginado)
# ============================================================
@router.get("/", response_model=InventoryMovementPaginated)
async def list_movements(
    page: int = 1,
    page_size: int = 10,
    product_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InventoryMovementPaginated:
    """
    Lista movimientos de inventario con paginación.

    GET /api/v1/inventory?page=1&page_size=10
    GET /api/v1/inventory?product_id=5&page=1

    El parámetro `product_id` es opcional:
    - Sin él: devuelve todos los movimientos del sistema
    - Con él: devuelve solo el historial de ese producto

    Los resultados vienen ordenados del más reciente al más viejo
    (mismo criterio que un extracto bancario).
    """
    skip = (page - 1) * page_size

    movements, total = await inventory_crud.get_movements(
        db,
        skip=skip,
        limit=page_size,
        product_id=product_id,
    )

    pages = math.ceil(total / page_size) if total > 0 else 0

    return InventoryMovementPaginated(
        items=[InventoryMovementResponse.model_validate(m) for m in movements],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ============================================================
# GET /api/v1/inventory/{movement_id} — Obtener un movimiento
# ============================================================
@router.get("/{movement_id}", response_model=InventoryMovementResponse)
async def get_movement(
    movement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InventoryMovementResponse:
    """
    Devuelve los datos de un movimiento específico.

    GET /api/v1/inventory/1
    """
    movement = await inventory_crud.get_movement_by_id(db, movement_id)

    if movement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movimiento con id '{movement_id}' no encontrado",
        )

    return InventoryMovementResponse.model_validate(movement)


# ============================================================
# POST /api/v1/inventory — Registrar un movimiento
# ============================================================
@router.post("/", response_model=InventoryMovementResponse, status_code=status.HTTP_201_CREATED)
async def register_movement(
    data: InventoryMovementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InventoryMovementResponse:
    """
    Registra un movimiento de inventario y actualiza el stock del producto.

    POST /api/v1/inventory
    Body: InventoryMovementCreate (JSON)
    Requiere: JWT válido (cualquier rol)

    Ejemplos de body:
      {"product_id": 1, "movement_type": "ENTRADA", "quantity": 50}
      {"product_id": 1, "movement_type": "SALIDA",  "quantity": 3, "notes": "Pedido #42"}
      {"product_id": 1, "movement_type": "AJUSTE",  "quantity": 45, "notes": "Conteo físico"}

    Posibles errores:
      404 → el producto no existe
      400 → el producto está inactivo, o stock insuficiente para SALIDA

    ¿Por qué llamamos al servicio y no al CRUD directamente?
    Porque registrar un movimiento no es una operación simple de BD.
    Requiere: validar el producto, calcular el nuevo stock, crear el
    movimiento Y actualizar el stock. Eso es lógica de negocio —
    responsabilidad del servicio, no del endpoint ni del CRUD.

    ¿Cómo llega `created_by_id` al servicio?
    El endpoint extrae `current_user.document_id` del objeto User
    que devuelve `get_current_user`. Ese document_id es la cédula
    del usuario logueado — nunca viene del body del cliente.
    """
    movement = await inventory_service.register_movement(
        db=db,
        data=data,
        created_by_id=current_user.document_id,
    )

    return InventoryMovementResponse.model_validate(movement)
