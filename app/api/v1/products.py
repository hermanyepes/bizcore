# ============================================================
# BizCore — Endpoints CRUD para productos
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore para productos.
# Reciben pedidos (HTTP requests), hablan con el bodeguero
# (crud/product.py), y entregan el resultado al cliente (response).
#
# Los meseros NO saben cómo funciona la BD — solo saben:
#   - Qué pedido llegó (parámetros de la request)
#   - Si el cliente tiene carnet (JWT validado por Depends)
#   - Si el cliente tiene permiso (rol: cualquiera vs solo admin)
#   - Qué traer del bodeguero (llaman a crud)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe POST /api/v1/products
#   2. Ejecuta las dependencias: get_db() → require_admin()
#   3. require_admin() verifica JWT y rol → si falla: 401 o 403
#   4. Llama al endpoint con db + admin ya resueltos
#   5. El endpoint verifica duplicados → llama a crud
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import product as product_crud
from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductPaginated,
    ProductResponse,
    ProductUpdate,
)

# prefix="/products": todas las rutas empiezan con /products
# Combinado con el prefijo del router principal → /api/v1/products
# tags=["products"]: agrupa los endpoints bajo "products" en Swagger (/docs)
router = APIRouter(prefix="/products", tags=["products"])


# ============================================================
# GET /api/v1/products — Listar productos (paginado)
# ============================================================
@router.get("/", response_model=ProductPaginated)
async def list_products(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # cualquier usuario autenticado
) -> ProductPaginated:
    """
    Lista todos los productos activos con paginación.

    GET /api/v1/products?page=1&page_size=10

    Solo devuelve productos con is_active=True.
    Los productos desactivados (soft delete) no aparecen aquí.

    ¿Por qué cualquier usuario autenticado puede listar productos?
    Porque los empleados también necesitan consultar el catálogo.
    Crear, editar y eliminar sí requiere ser Administrador.
    """
    # Convertir page/page_size a skip/limit (los parámetros nativos de SQL)
    # Ejemplo: page=2, page_size=10 → skip=10 (saltar los primeros 10)
    skip = (page - 1) * page_size

    products, total = await product_crud.get_products(db, skip=skip, limit=page_size)

    # math.ceil redondea hacia arriba: 11 productos / 10 por página = 2 páginas
    pages = math.ceil(total / page_size) if total > 0 else 0

    return ProductPaginated(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


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
    product = await product_crud.get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con id '{product_id}' no encontrado",
        )
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

    ¿Por qué verificar el nombre duplicado antes de insertar?
    `name` tiene unique=True en la BD. Si no verificamos aquí,
    PostgreSQL lanzaría un IntegrityError que FastAPI convierte en
    un 500 genérico — un error confuso para el cliente.
    Es mejor detectarlo nosotros y devolver un 409 claro.
    """
    # Verificar que no exista ya un producto con ese nombre
    existing = await product_crud.get_product_by_name(db, data.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un producto con el nombre '{data.name}'",
        )

    product = await product_crud.create_product(db, data)
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
    # Si el cliente quiere renombrar el producto, verificar que el
    # nuevo nombre no esté siendo usado por otro producto.
    if data.name is not None:
        existing = await product_crud.get_product_by_name(db, data.name)
        if existing is not None and existing.id != product_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un producto con el nombre '{data.name}'",
            )

    product = await product_crud.update_product(db, product_id, data)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con id '{product_id}' no encontrado",
        )
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
    product = await product_crud.delete_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con id '{product_id}' no encontrado",
        )
    return ProductResponse.model_validate(product)
