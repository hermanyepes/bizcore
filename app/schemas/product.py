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


class ProductCreate(BaseModel):
    """
    Datos necesarios para registrar un producto nuevo.

    POST /api/v1/products
    Solo el Administrador puede crear productos (validado en el endpoint).

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


class ProductResponse(BaseModel):
    """
    Datos del producto que la API devuelve al cliente.

    GET /api/v1/products
    GET /api/v1/products/{id}

    Incluye `id` y `created_at` porque ya los generó la BD.
    Incluye todos los campos — los productos no tienen datos sensibles
    que ocultar (a diferencia de User que tiene password_hash).

    model_config = ConfigDict(from_attributes=True):
    Le dice a Pydantic que puede construir este schema desde un objeto
    SQLAlchemy (que tiene atributos, no es un diccionario).
    Sin esto, Pydantic intentaría leerlo como dict y fallaría.
    """

    id: int
    name: str
    description: str | None
    price: int
    stock: int
    category: str | None
    is_active: bool
    created_at: datetime

    # Permite crear este schema desde un objeto SQLAlchemy:
    # ProductResponse.model_validate(product_obj)
    model_config = ConfigDict(from_attributes=True)


class ProductPaginated(BaseModel):
    """
    Respuesta paginada para el listado de productos.

    ANALOGÍA: como el catálogo de una tienda por páginas.
    No traes todo el catálogo — traes una página y sabes cuántas hay.

    GET /api/v1/products?page=1&page_size=10
    """

    items: list[ProductResponse]   # productos de esta página
    total: int                     # total de productos en la BD
    page: int                      # página actual
    page_size: int                 # cuántos productos por página
    pages: int                     # total de páginas
