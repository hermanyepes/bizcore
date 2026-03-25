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
#   - Si el cliente tiene permiso (rol: cualquiera vs solo admin)
#   - A quién llamar en la cocina (product_service)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe POST /api/v1/products
#   2. Ejecuta las dependencias: get_db() → require_admin()
#   3. require_admin() verifica JWT y rol → si falla: 401 o 403
#   4. Llama al endpoint con db + admin ya resueltos
#   5. El endpoint delega en product_service → service llama al crud
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductPaginated,
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
@router.get("/", response_model=ProductPaginated)
async def list_products(
    page: int = Query(default=1, ge=1),               # mínimo página 1
    page_size: int = Query(default=10, ge=1, le=100), # entre 1 y 100 registros
    is_active: bool | None = Query(default=None),     # True/False/None (todos)
    category: str | None = Query(default=None),       # ej: 'Bebidas', 'Snacks'
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),   # cualquier usuario autenticado
) -> ProductPaginated:
    """
    Lista productos con paginación y filtros opcionales.

    GET /api/v1/products?page=1&page_size=10
    GET /api/v1/products?is_active=true              ← catálogo activo
    GET /api/v1/products?category=Bebidas&is_active=true
    GET /api/v1/products?is_active=false             ← productos desactivados (admin)

    Filtros opcionales — si no se envían, devuelve todos los registros.
    """
    return await product_service.list(db, page, page_size, is_active, category)


# ============================================================
# GET /api/v1/products/{id} — Obtener un producto
# ============================================================
@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductResponse:
    """
    Devuelve los datos de un producto específico.

    GET /api/v1/products/1

    ¿Por qué product_id es int y document_id era str?
    Porque el id de Product es autoincremental (entero).
    FastAPI automáticamente convierte "1" (string de la URL) a int.
    Si alguien envía /products/abc, FastAPI devuelve 422 antes de
    llegar al endpoint — "abc" no es un entero válido.
    """
    product = await product_service.get(db, product_id)
    return ProductResponse.model_validate(product)


# ============================================================
# POST /api/v1/products — Crear producto (solo Administrador)
# ============================================================
@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # solo Administrador puede crear
) -> ProductResponse:
    """
    Registra un nuevo producto en el catálogo.

    POST /api/v1/products
    Body: ProductCreate (JSON)
    Requiere: JWT con rol Administrador

    ¿Por qué 201 y no 200?
    200 OK      → éxito, el recurso ya existía
    201 Created → éxito, se creó un nuevo recurso
    POST que crea algo siempre devuelve 201.
    """
    product = await product_service.create(db, data)
    return ProductResponse.model_validate(product)


# ============================================================
# PUT /api/v1/products/{id} — Actualizar producto (solo Administrador)
# ============================================================
@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ProductResponse:
    """
    Actualiza los datos de un producto. Solo se modifican los campos enviados.

    PUT /api/v1/products/1
    Body: ProductUpdate (solo los campos que quieres cambiar)
    Requiere: JWT con rol Administrador

    Ejemplos de uso:
    - Subir el precio:           {"price": 28000}
    - Actualizar el stock:       {"stock": 150}
    - Desactivar el producto:    {"is_active": false}
    - Cambiar nombre y precio:   {"name": "Café Premium", "price": 32000}
    """
    product = await product_service.update(db, product_id, data)
    return ProductResponse.model_validate(product)


# ============================================================
# DELETE /api/v1/products/{id} — Desactivar producto (solo Administrador)
# ============================================================
@router.delete("/{product_id}", response_model=ProductResponse)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ProductResponse:
    """
    Desactiva un producto (soft delete — no borra el registro de la BD).

    DELETE /api/v1/products/1
    Requiere: JWT con rol Administrador

    La respuesta devuelve el producto con is_active=False,
    confirmando visualmente que fue desactivado.

    ¿Por qué no borrarlo definitivamente?
    En fases futuras (Órdenes, Inventario), habrá registros históricos
    que referencian este producto. Si lo borramos, esos registros
    quedarían huérfanos — sin producto al que apuntar.
    """
    product = await product_service.delete(db, product_id)
    return ProductResponse.model_validate(product)
