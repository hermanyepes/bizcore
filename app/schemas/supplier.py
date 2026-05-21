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

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import PaginatedResponse

# ============================================================
# Validador NIT colombiano — algoritmo oficial DIAN
# ============================================================
#
# Pesos para el módulo 11, aplicados de derecha a izquierda
# sobre cada dígito del NIT (sin el DV).
#
# Ejemplo: NIT 899999230, DV esperado = 7
#   0*3 + 3*7 + 2*13 + 9*17 + 9*19 + 9*23 + 9*29 + 9*37 + 8*41
#   = 0 + 21 + 26 + 153 + 171 + 207 + 261 + 333 + 328 = 1500
#   1500 % 11 = 4  →  11 - 4 = 7 ✓
#
_NIT_WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
_NIT_PATTERN = re.compile(r"^(\d{9,11})(?:-(\d))?$")


def _compute_nit_dv(digits: str) -> int:
    """Calcula el dígito de verificación según el algoritmo DIAN módulo 11."""
    total = sum(int(d) * w for d, w in zip(reversed(digits), _NIT_WEIGHTS))
    rem = total % 11
    return rem if rem <= 1 else 11 - rem


def _validate_nit_value(v: str | None) -> str | None:
    """
    Valida que el NIT tenga el formato correcto y, si incluye DV, que sea correcto.
    Usado como validator compartido en SupplierCreate y SupplierUpdate.
    """
    if v is None:
        return v
    v = v.strip()
    match = _NIT_PATTERN.match(v)
    if not match:
        raise ValueError(
            "NIT inválido: debe tener 9-11 dígitos, opcionalmente seguido de '-' "
            "y el dígito de verificación (ej: 800123456 o 800123456-7)."
        )
    body, dv = match.group(1), match.group(2)
    if dv is not None:
        expected = _compute_nit_dv(body)
        if expected != int(dv):
            raise ValueError(
                f"Dígito de verificación incorrecto. "
                f"Para el NIT {body} el DV correcto es {expected}."
            )
    return v


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
    nit: str | None = Field(default=None, max_length=15)

    @field_validator("nit")
    @classmethod
    def validate_nit(cls, v: str | None) -> str | None:
        return _validate_nit_value(v)


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
    nit: str | None = Field(default=None, max_length=15)

    # is_active=False activa el soft delete desde el endpoint de actualización.
    # Mismo patrón que ProductUpdate: un solo endpoint maneja edición y desactivación.
    is_active: bool | None = None

    @field_validator("nit")
    @classmethod
    def validate_nit(cls, v: str | None) -> str | None:
        return _validate_nit_value(v)


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
    nit: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None  # NULL si nunca fue actualizado

    model_config = ConfigDict(from_attributes=True)


# Especialización del schema genérico para proveedores.
# Equivale a una clase con items: list[SupplierResponse], total, page, page_size, pages.
SupplierPaginated = PaginatedResponse[SupplierResponse]
