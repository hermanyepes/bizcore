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
#   - Si el cliente tiene permiso (rol: Supervisor+ vs Admin+)
#   - A quién llamar en la cocina (supplier_service)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# PERMISOS POR ACCIÓN (ver docs/roles/matriz-permisos.md sección 2.4):
#   GET  /suppliers        → Supervisor+ (require_supervisor) — Empleados no ven proveedores
#   GET  /suppliers/{id}   → Supervisor+
#   POST /suppliers        → Supervisor+ (Supervisor puede gestionar proveedores)
#   PUT  /suppliers/{id}   → Supervisor+
#   DELETE /suppliers/{id} → Admin+ (require_admin) — soft delete requiere más privilegio
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe POST /api/v1/suppliers
#   2. Ejecuta get_db() → require_supervisor()
#   3. require_supervisor() verifica JWT y rol → si falla: 401 o 403
#   4. Llama al endpoint con db + current_user ya resueltos
#   5. El endpoint delega en supplier_service → service llama al crud
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limiter import limiter
from app.dependencies import get_db, require_admin, require_supervisor
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
@limiter.limit(settings.AUTHENTICATED_RATE_LIMIT)
async def list_suppliers(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    page: int = Query(default=1, ge=1),  # mínimo página 1
    page_size: int = Query(default=10, ge=1, le=100),  # entre 1 y 100 registros
    is_active: bool | None = Query(default=None),  # True/False/None (todos)
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_supervisor),  # Supervisor+ puede ver proveedores
) -> SupplierPaginated:
    """
    Lista proveedores con paginación y filtro opcional.

    GET /api/v1/suppliers?page=1&page_size=10
    GET /api/v1/suppliers?is_active=true    ← solo activos
    GET /api/v1/suppliers?is_active=false   ← solo desactivados (admin)
    Requiere: JWT con rol Supervisor, Administrador o Superadmin
    """
    return await supplier_service.list(db, page, page_size, is_active)


# ============================================================
# GET /api/v1/suppliers/{id} — Obtener un proveedor
# ============================================================
@router.get("/{supplier_id}", response_model=SupplierResponse)
@limiter.limit(settings.AUTHENTICATED_RATE_LIMIT)
async def get_supplier(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_supervisor),  # Supervisor+ puede ver proveedores
) -> SupplierResponse:
    """
    Devuelve los datos de un proveedor específico.

    GET /api/v1/suppliers/1
    Requiere: JWT con rol Supervisor, Administrador o Superadmin

    Si supplier_id no existe en la BD → 404.
    Si el token JWT es inválido o no se envía → 401.
    """
    supplier = await supplier_service.get(db, supplier_id)
    return SupplierResponse.model_validate(supplier)


# ============================================================
# POST /api/v1/suppliers — Crear proveedor (Supervisor o superior)
# ============================================================
@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_supplier(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_supervisor),  # Supervisor+ puede crear proveedores
) -> SupplierResponse:
    """
    Registra un nuevo proveedor en la BD.

    POST /api/v1/suppliers
    Body: SupplierCreate (JSON)
    Requiere: JWT con rol Supervisor, Administrador o Superadmin

    ¿Por qué 201 y no 200?
    200 OK      → éxito, el recurso ya existía
    201 Created → éxito, se creó un nuevo recurso
    POST que crea algo siempre devuelve 201.
    """
    supplier = await supplier_service.create(db, data)
    return SupplierResponse.model_validate(supplier)


# ============================================================
# PUT /api/v1/suppliers/{id} — Actualizar proveedor (Supervisor o superior)
# ============================================================
@router.put("/{supplier_id}", response_model=SupplierResponse)
@limiter.limit("30/minute")
async def update_supplier(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    supplier_id: int,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_supervisor),  # Supervisor+ puede actualizar proveedores
) -> SupplierResponse:
    """
    Actualiza los datos de un proveedor. Solo se modifican los campos enviados.

    PUT /api/v1/suppliers/1
    Body: SupplierUpdate (solo los campos que quieres cambiar)
    Requiere: JWT con rol Supervisor, Administrador o Superadmin

    Ejemplos de uso:
    - Actualizar teléfono:      {"phone": "310 555 9999"}
    - Desactivar proveedor:     {"is_active": false}
    - Cambiar nombre y email:   {"name": "Nuevo Nombre", "contact_email": "nuevo@mail.com"}
    """
    supplier = await supplier_service.update(db, supplier_id, data)
    return SupplierResponse.model_validate(supplier)


# ============================================================
# DELETE /api/v1/suppliers/{id} — Desactivar proveedor (solo Admin+)
# ============================================================
@router.delete("/{supplier_id}", response_model=SupplierResponse)
@limiter.limit("30/minute")
async def delete_supplier(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # solo Admin+ — soft delete es una decisión administrativa
) -> SupplierResponse:
    """
    Desactiva un proveedor (soft delete — no borra el registro de la BD).

    DELETE /api/v1/suppliers/1
    Requiere: JWT con rol Administrador o Superadmin

    La respuesta devuelve el proveedor con is_active=False,
    confirmando visualmente que fue desactivado.

    ¿Por qué soft delete?
    En Phase 5, los pedidos referenciarán proveedores. Si borramos
    la fila, esos registros históricos quedarían huérfanos.
    """
    supplier = await supplier_service.delete(db, supplier_id)
    return SupplierResponse.model_validate(supplier)
