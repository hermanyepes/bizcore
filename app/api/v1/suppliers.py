# ============================================================
# BizCore — Endpoints CRUD para proveedores
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore para proveedores.
# Reciben pedidos (HTTP requests), hablan con el chef
# (services/supplier.py), y entregan el resultado al cliente (response).
#
# El mesero NO cocina ni valida reglas de negocio.
# Solo sabe:
#   - Qué pedido llegó (parámetros de la request)
#   - Si el cliente tiene carnet (JWT validado por Depends)
#   - Si el cliente tiene permiso (rol: cualquiera vs solo admin)
#   - A quién llamar en la cocina (supplier_service)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe POST /api/v1/suppliers
#   2. Ejecuta las dependencias: get_db() → require_admin()
#   3. require_admin() verifica JWT y rol → si falla: 401 o 403
#   4. Llama al endpoint con db + admin ya resueltos
#   5. El endpoint delega en supplier_service → service llama al crud
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.supplier import (
    SupplierCreate,
    SupplierPaginated,
    SupplierResponse,
    SupplierUpdate,
)
from app.services.supplier import supplier_service

# prefix="/suppliers": todas las rutas empiezan con /suppliers
# Combinado con el prefijo del router principal → /api/v1/suppliers
# tags=["suppliers"]: agrupa los endpoints bajo "suppliers" en Swagger (/docs)
router = APIRouter(prefix="/suppliers", tags=["suppliers"])


# ============================================================
# GET /api/v1/suppliers — Listar proveedores (paginado)
# ============================================================
@router.get("/", response_model=SupplierPaginated)
async def list_suppliers(
    page: int = Query(default=1, ge=1),               # mínimo página 1
    page_size: int = Query(default=10, ge=1, le=100), # entre 1 y 100 registros
    is_active: bool | None = Query(default=None),     # True/False/None (todos)
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),   # cualquier usuario autenticado
) -> SupplierPaginated:
    """
    Lista proveedores con paginación y filtro opcional.

    GET /api/v1/suppliers?page=1&page_size=10
    GET /api/v1/suppliers?is_active=true    ← solo activos
    GET /api/v1/suppliers?is_active=false   ← solo desactivados (admin)
    """
    return await supplier_service.list(db, page, page_size, is_active)


# ============================================================
# GET /api/v1/suppliers/{id} — Obtener un proveedor
# ============================================================
@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SupplierResponse:
    """
    Devuelve los datos de un proveedor específico.

    GET /api/v1/suppliers/1

    Si supplier_id no existe en la BD → 404.
    Si el token JWT es inválido o no se envía → 401.
    """
    supplier = await supplier_service.get(db, supplier_id)
    return SupplierResponse.model_validate(supplier)


# ============================================================
# POST /api/v1/suppliers — Crear proveedor (solo Administrador)
# ============================================================
@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # solo Administrador puede crear
) -> SupplierResponse:
    """
    Registra un nuevo proveedor en la BD.

    POST /api/v1/suppliers
    Body: SupplierCreate (JSON)
    Requiere: JWT con rol Administrador

    ¿Por qué 201 y no 200?
    200 OK      → éxito, el recurso ya existía
    201 Created → éxito, se creó un nuevo recurso
    POST que crea algo siempre devuelve 201.
    """
    supplier = await supplier_service.create(db, data)
    return SupplierResponse.model_validate(supplier)


# ============================================================
# PUT /api/v1/suppliers/{id} — Actualizar proveedor (solo Administrador)
# ============================================================
@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> SupplierResponse:
    """
    Actualiza los datos de un proveedor. Solo se modifican los campos enviados.

    PUT /api/v1/suppliers/1
    Body: SupplierUpdate (solo los campos que quieres cambiar)
    Requiere: JWT con rol Administrador

    Ejemplos de uso:
    - Actualizar teléfono:      {"phone": "310 555 9999"}
    - Desactivar proveedor:     {"is_active": false}
    - Cambiar nombre y email:   {"name": "Nuevo Nombre", "contact_email": "nuevo@mail.com"}
    """
    supplier = await supplier_service.update(db, supplier_id, data)
    return SupplierResponse.model_validate(supplier)


# ============================================================
# DELETE /api/v1/suppliers/{id} — Desactivar proveedor (solo Administrador)
# ============================================================
@router.delete("/{supplier_id}", response_model=SupplierResponse)
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> SupplierResponse:
    """
    Desactiva un proveedor (soft delete — no borra el registro de la BD).

    DELETE /api/v1/suppliers/1
    Requiere: JWT con rol Administrador

    La respuesta devuelve el proveedor con is_active=False,
    confirmando visualmente que fue desactivado.

    ¿Por qué soft delete?
    En Phase 5, los pedidos referenciarán proveedores. Si borramos
    la fila, esos registros históricos quedarían huérfanos.
    """
    supplier = await supplier_service.delete(db, supplier_id)
    return SupplierResponse.model_validate(supplier)
