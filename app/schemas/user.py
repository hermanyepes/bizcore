# ============================================================
# BizCore — Schemas Pydantic para User
# ============================================================
#
# ANALOGÍA: si el modelo SQLAlchemy (models/user.py) es la
# ficha interna de un empleado en RRHH con TODO su historial,
# estos schemas son los distintos formularios que existen:
#
#   UserCreate    = formulario de contratación (lo llena el admin)
#   UserUpdate    = formulario de actualización de datos
#   UserResponse  = lo que aparece en el directorio de la empresa
#                   (sin datos confidenciales como la contraseña)
#
# DIFERENCIA CLAVE con el modelo SQLAlchemy:
#   Modelo:   password_hash  ← lo que se guarda en la BD
#   Schema:   password        ← lo que recibe del cliente (texto plano)
#             (en UserResponse no aparece ninguno de los dos)
#
# ============================================================

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.constants import UserRole
from app.schemas.common import PaginatedResponse


class UserCreate(BaseModel):
    """
    Datos necesarios para crear un nuevo usuario.

    POST /api/v1/users
    Solo Administrador o Superadmin puede crear usuarios (validado en el endpoint).

    ¿Por qué UserRole y no Literal?
    UserRole es un StrEnum con los 4 roles del sistema. Pydantic rechaza
    automáticamente cualquier valor fuera del enum. Usar UserRole en vez
    de Literal centraliza la definición en app.constants — si se añade
    un rol nuevo, solo hay que tocarlo en un lugar.
    """

    document_id: str = Field(max_length=20)
    document_type: str = Field(max_length=10)
    full_name: str = Field(max_length=80)
    phone: str | None = Field(default=None, max_length=15)
    email: EmailStr
    city: str | None = Field(default=None, max_length=50)
    role: UserRole
    # El cliente envía la contraseña en texto plano.
    # El endpoint la hashea antes de guardar — nunca toca la BD sin hashear.
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    """
    Datos que se pueden actualizar. Todos son opcionales.

    PUT /api/v1/users/{document_id}

    ¿Por qué todos opcionales?
    Porque el cliente puede querer actualizar solo el teléfono sin
    enviar todos los demás campos. Si fueran obligatorios, el cliente
    tendría que enviar toda la información del usuario para cambiar
    una sola cosa.

    Los campos que NO están aquí (document_id, email, created_at)
    no se pueden cambiar por diseño.
    """

    full_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=15)
    city: str | None = Field(default=None, max_length=50)
    role: UserRole | None = None
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None


class UserResponse(BaseModel):
    """
    Datos del usuario que la API devuelve al cliente.

    GET /api/v1/users
    GET /api/v1/users/{document_id}

    Nótese lo que NO está aquí: password_hash.
    Aunque el objeto User de la BD tenga ese campo, Pydantic
    solo incluye en la respuesta los campos definidos en este schema.
    El hash nunca sale de la API.

    model_config = ConfigDict(from_attributes=True):
    Le dice a Pydantic que puede construir este schema a partir de
    un objeto SQLAlchemy (que tiene atributos, no es un diccionario).
    Sin esto, Pydantic intentaría leerlo como dict y fallaría.
    """

    document_id: str
    document_type: str
    full_name: str
    phone: str | None
    email: str
    city: str | None
    role: str
    join_date: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime | None  # NULL si nunca fue actualizado

    # Permite crear este schema desde un objeto SQLAlchemy:
    # UserResponse.model_validate(user_obj)
    model_config = ConfigDict(from_attributes=True)


# Especialización del schema genérico para usuarios.
# Equivale a una clase con items: list[UserResponse], total, page, page_size, pages.
UserPaginated = PaginatedResponse[UserResponse]
