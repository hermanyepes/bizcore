# ============================================================
# BizCore — Endpoints CRUD para productos
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore para productos.
# Reciben pedidos (HTTP requests), hablan con el chef
# (services/product.py), y entregan el resultado al cliente (response).
#
# El mesero NO cocina ni valida reglas de negocio.
# Solo sabe:
#   - Qué pedido llegó (parámetros de la request)
#   - Si el cliente tiene carnet (JWT validado por Depends)
#   - Si el cliente tiene permiso (rol: cualquiera vs Supervisor+ vs Admin+)
#   - A quién llamar en la cocina (product_service)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe POST /api/v1/products
#   2. Ejecuta las dependencias: get_db() → require_supervisor()
#   3. require_supervisor() verifica JWT y rol → si falla: 401 o 403
#   4. Llama al endpoint con db + admin ya resueltos
#   5. El endpoint delega en product_service → service llama al crud
#   6. FastAPI serializa la respuesta con response_model
#
# PERMISOS POR ACCIÓN (ver docs/roles/matriz-permisos.md sección 2.2):
#   GET  /products     → cualquier autenticado (get_current_user)
#   GET  /products/{id}→ cualquier autenticado
#   POST /products     → Supervisor+ (require_supervisor)
#   PUT  /products/{id}→ Supervisor+ (require_supervisor)
#   DELETE /products/{id}→ Admin+  (require_admin) — soft delete es irreversible
#
# ============================================================

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.crud import product as product_crud
from app.dependencies import get_current_user, get_db, require_admin, require_supervisor
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.product import (
    ProductBaseResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductResponse,
    ProductUpdate,
)
from app.services.product import product_service

# prefix="/products": todas las rutas empiezan con /products
# Combinado con el prefijo del router principal → /api/v1/products
# tags=["products"]: agrupa los endpoints bajo "products" en Swagger (/docs)
router = APIRouter(prefix="/products", tags=["products"])


# ============================================================
# GET /api/v1/products — Listar productos (paginado)
# ============================================================
@router.get("/")
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista productos con paginación y filtros opcionales.

    Column-level security (HU-022):
    - Empleado     → ProductBaseResponse (sin cost_price ni margin)
    - Supervisor+  → ProductDetailResponse (con cost_price y margin)

    GET /api/v1/products?page=1&page_size=10
    GET /api/v1/products?is_active=true
    GET /api/v1/products?category=Bebidas&is_active=true
    """
    skip = (page - 1) * page_size
    products, total = await product_crud.get_products(
        db, skip=skip, limit=page_size, is_active=is_active, category=category
    )
    pages = math.ceil(total / page_size) if total > 0 else 0

    if current_user.role == UserRole.EMPLOYEE:
        items = [ProductBaseResponse.model_validate(p) for p in products]
    else:
        items = [ProductDetailResponse.model_validate(p) for p in products]

    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=pages
    )


# ============================================================
# GET /api/v1/products/{id} — Obtener un producto
# ============================================================
@router.get("/{product_id}")
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductBaseResponse | ProductDetailResponse:
    """
    Devuelve los datos de un producto específico.

    Column-level security (HU-022):
    - Empleado     → ProductBaseResponse (sin cost_price ni margin)
    - Supervisor+  → ProductDetailResponse (con cost_price y margin)

    GET /api/v1/products/1
    """
    product = await product_service.get(db, product_id)
    if current_user.role == UserRole.EMPLOYEE:
        return ProductBaseResponse.model_validate(product)
    return ProductDetailResponse.model_validate(product)


# ============================================================
# POST /api/v1/products — Crear producto (Supervisor o superior)
# ============================================================
@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_supervisor),  # Supervisor, Admin o Superadmin
) -> ProductResponse:
    """
    Registra un nuevo producto en el catálogo.

    POST /api/v1/products
    Body: ProductCreate (JSON)
    Requiere: JWT con rol Supervisor, Administrador o Superadmin

    ¿Por qué 201 y no 200?
    200 OK      → éxito, el recurso ya existía
    201 Created → éxito, se creó un nuevo recurso
    POST que crea algo siempre devuelve 201.
    """
    product = await product_service.create(db, data)
    return ProductResponse.model_validate(product)


# ============================================================
# PUT /api/v1/products/{id} — Actualizar producto (Supervisor o superior)
# ============================================================
@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_supervisor),  # Supervisor, Admin o Superadmin
) -> ProductResponse:
    """
    Actualiza los datos de un producto. Solo se modifican los campos enviados.

    PUT /api/v1/products/1
    Body: ProductUpdate (solo los campos que quieres cambiar)
    Requiere: JWT con rol Supervisor, Administrador o Superadmin

    Ejemplos de uso:
    - Subir el precio:           {"price": 28000}
    - Actualizar el stock:       {"stock": 150}
    - Desactivar el producto:    {"is_active": false}
    - Cambiar nombre y precio:   {"name": "Café Premium", "price": 32000}
    """
    product = await product_service.update(db, product_id, data)
    return ProductResponse.model_validate(product)


# ============================================================
# DELETE /api/v1/products/{id} — Desactivar producto (solo Admin+)
# ============================================================
@router.delete("/{product_id}", response_model=ProductResponse)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # solo Admin o Superadmin — soft delete irreversible
) -> ProductResponse:
    """
    Desactiva un producto (soft delete — no borra el registro de la BD).

    DELETE /api/v1/products/1
    Requiere: JWT con rol Administrador o Superadmin

    ¿Por qué DELETE requiere más permiso que POST/PUT?
    Desactivar un producto lo oculta del catálogo para todos los usuarios.
    Es una decisión más impactante que editar un campo — requiere Admin+.

    La respuesta devuelve el producto con is_active=False,
    confirmando visualmente que fue desactivado.

    ¿Por qué no borrarlo definitivamente?
    En fases futuras (Órdenes, Inventario), habrá registros históricos
    que referencian este producto. Si lo borramos, esos registros
    quedarían huérfanos — sin producto al que apuntar.
    """
    product = await product_service.delete(db, product_id)
    return ProductResponse.model_validate(product)
