# ============================================================
# BizCore — Schemas Pydantic para Supplier
# ============================================================
#
# ANALOGÍA: si el modelo SQLAlchemy es la ficha interna del
# proveedor en la libreta de la bodega, estos schemas son los
# distintos formularios según la situación:
#
#   SupplierCreate    = formulario para registrar un proveedor nuevo
#   SupplierUpdate    = formulario para modificar sus datos
#   SupplierResponse  = ficha que la API devuelve al cliente
#   SupplierPaginated = listado paginado de proveedores
#
# DIFERENCIA CLAVE con el modelo SQLAlchemy:
#   Modelo: tiene `id` y `created_at` generados por la BD
#   SupplierCreate: NO los incluye (los genera la BD, no el cliente)
#   SupplierResponse: SÍ los incluye (la BD ya los generó)
#
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SupplierCreate(BaseModel):
    """
    Datos necesarios para registrar un proveedor nuevo.

    POST /api/v1/suppliers
    Solo el Administrador puede crear proveedores (validado en el endpoint).

    Campos ausentes deliberadamente:
    - `id`: lo genera PostgreSQL automáticamente (autoincrement)
    - `created_at`: lo genera PostgreSQL con server_default=func.now()
    - `is_active`: siempre empieza en True — un proveedor recién creado
      está activo por definición.
    """

    name: str = Field(max_length=150)

    # EmailStr: Pydantic valida que el formato sea un email real
    # (tiene "@", dominio, extensión). Rechaza "no-es-un-email".
    # default=None: el campo es opcional — no todo proveedor tiene email.
    contact_email: EmailStr | None = Field(default=None)

    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)


class SupplierUpdate(BaseModel):
    """
    Datos que se pueden actualizar. Todos son opcionales.

    PUT /api/v1/suppliers/{id}

    ¿Por qué todos opcionales?
    El admin puede querer actualizar solo el teléfono sin tocar el nombre.
    Con todos opcionales, envía únicamente los campos que cambian.
    El endpoint usa exclude_unset=True para no pisar los demás.
    """

    name: str | None = Field(default=None, max_length=150)
    contact_email: EmailStr | None = Field(default=None)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)

    # is_active=False activa el soft delete desde el endpoint de actualización.
    # Mismo patrón que ProductUpdate: un solo endpoint maneja edición y desactivación.
    is_active: bool | None = None


class SupplierResponse(BaseModel):
    """
    Datos del proveedor que la API devuelve al cliente.

    GET /api/v1/suppliers
    GET /api/v1/suppliers/{id}

    Incluye `id` y `created_at` porque ya los generó la BD.
    No hay campos sensibles que ocultar en un proveedor.

    from_attributes=True: permite construir este schema desde un
    objeto SQLAlchemy (que tiene atributos, no es un diccionario).
    """

    id: int
    name: str
    contact_email: str | None
    phone: str | None
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None  # NULL si nunca fue actualizado

    model_config = ConfigDict(from_attributes=True)


class SupplierPaginated(BaseModel):
    """
    Respuesta paginada para el listado de proveedores.

    GET /api/v1/suppliers?page=1&page_size=10

    Mismo patrón que ProductPaginated: devolver una página
    en vez de todos los registros de golpe.
    """

    items: list[SupplierResponse]  # proveedores de esta página
    total: int                     # total de proveedores en la BD
    page: int                      # página actual
    page_size: int                 # cuántos proveedores por página
    pages: int                     # total de páginas
