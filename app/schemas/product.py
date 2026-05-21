# ============================================================
# BizCore — Schemas Pydantic para Product
# ============================================================
#
# ANALOGÍA: si el modelo SQLAlchemy (models/product.py) es la
# ficha interna del producto en la bodega con TODO su historial,
# estos schemas son los distintos formularios que existen:
#
#   ProductCreate    = formulario de ingreso al catálogo
#   ProductUpdate    = formulario de modificación de datos
#   ProductResponse  = ficha pública del producto (lo que ve el cliente)
#   ProductPaginated = catálogo paginado (página X de Y)
#
# DIFERENCIA CLAVE con el modelo SQLAlchemy:
#   Modelo: tiene `id` y `created_at` generados por la BD
#   ProductCreate: NO los incluye (el cliente no los envía, los genera la BD)
#   ProductResponse: SÍ los incluye (la BD ya los generó, se los mostramos)
#
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse


class ProductCreate(BaseModel):
    """
    Datos necesarios para registrar un producto nuevo.

    POST /api/v1/products
    Solo el Supervisor+ puede crear productos (validado en el endpoint).

    Campos ausentes deliberadamente:
    - `id`: lo genera PostgreSQL automáticamente (autoincrement)
    - `created_at`: lo genera PostgreSQL con server_default=func.now()
    - `is_active`: siempre empieza en True — un producto recién creado
      está activo por definición. No tiene sentido crear uno inactivo.
    """

    name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=500)

    # gt=0: "greater than 0" — el precio debe ser mayor a cero.
    # Pydantic rechaza automáticamente precio=0 o precio=-500.
    # No tiene sentido registrar un producto sin precio o con precio negativo.
    price: int = Field(gt=0)

    # ge=0: "greater than or equal to 0" — el stock puede ser cero
    # (producto agotado pero registrado), pero no negativo.
    # default=0: si no se envía, empieza en cero. Campo opcional.
    stock: int = Field(default=0, ge=0)

    category: str | None = Field(default=None, max_length=60)

    # cost_price y margin: opcionales al crear. El Supervisor registra
    # el costo de compra para calcular el margen. El Empleado no los envía.
    cost_price: int | None = Field(default=None, gt=0)
    margin: int | None = Field(default=None, ge=0)


class ProductUpdate(BaseModel):
    """
    Datos que se pueden actualizar. Todos son opcionales.

    PUT /api/v1/products/{id}

    ¿Por qué todos opcionales?
    El admin puede querer actualizar solo el precio sin tocar el nombre,
    la descripción o el stock. Si fueran obligatorios, tendría que
    re-enviar todos los campos para cambiar uno solo.

    Los campos ausentes (id, created_at) no se pueden cambiar por diseño.
    """

    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    price: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=60)
    # is_active permite hacer soft delete desde el endpoint de actualización:
    # enviar is_active=False desactiva el producto sin borrarlo de la BD.
    is_active: bool | None = None
    cost_price: int | None = Field(default=None, gt=0)
    margin: int | None = Field(default=None, ge=0)


class ProductBaseResponse(BaseModel):
    """
    Campos del producto visibles para TODOS los roles autenticados.

    GET /api/v1/products       → Empleado recibe esta versión
    GET /api/v1/products/{id}  → ídem

    Excluye deliberadamente cost_price y margin — son datos financieros
    internos que el Empleado no necesita para operar. Ver HU-022.
    """

    id: int
    name: str
    description: str | None
    price: int
    stock: int
    category: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ProductDetailResponse(ProductBaseResponse):
    """
    Campos completos del producto — para Supervisor, Administrador y Superadmin.

    Hereda todos los campos de ProductBaseResponse y añade:
    - cost_price: costo de compra del producto (confidencial)
    - margin: margen calculado (confidencial)

    El endpoint devuelve esta clase cuando current_user.role != "Empleado".
    """

    cost_price: int | None = None
    margin: int | None = None


# Alias de compatibilidad — lo usan los endpoints de POST/PUT/DELETE
# que siempre responden con el detalle completo (solo los accede Supervisor+).
ProductResponse = ProductDetailResponse

# Especialización del schema genérico para productos.
# Equivale a una clase con items: list[ProductDetailResponse], total, page, page_size, pages.
ProductPaginated = PaginatedResponse[ProductDetailResponse]
