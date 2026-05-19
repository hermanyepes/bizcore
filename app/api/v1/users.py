# ============================================================
# BizCore — Endpoints CRUD para usuarios
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore.
# Reciben pedidos (HTTP requests), hablan con el chef
# (services/user.py), y entregan el resultado al cliente (response).
#
# El mesero NO cocina ni valida reglas de negocio.
# Solo sabe:
#   - Qué pedido llegó (parámetros de la request)
#   - Si el cliente tiene carnet (JWT validado por Depends)
#   - A quién llamar en la cocina (user_service)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe GET /api/v1/users/1000000001
#   2. Ejecuta las dependencias: get_db() → require_admin()
#   3. require_admin() verifica el JWT y el rol → si falla: 401 o 403
#   4. Llama al endpoint con db + current_user ya resueltos
#   5. El endpoint delega en user_service → user_service llama al crud
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.core.config import settings
from app.core.exceptions import PermissionDeniedError
from app.core.limiter import limiter
from app.dependencies import get_current_user, get_db, require_admin, require_superadmin
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserPaginated,
    UserResponse,
    UserUpdateSuperadmin,
)
from app.services.user import user_service

# prefix="/users": todas las rutas empiezan con /users
# Combinado con el prefijo del router principal → /api/v1/users
# tags=["users"]: agrupa los endpoints bajo "users" en Swagger (/docs)
router = APIRouter(prefix="/users", tags=["users"])


# ============================================================
# GET /api/v1/users — Listar usuarios (paginado)
# ============================================================
@router.get("/", response_model=UserPaginated)
@limiter.limit(settings.AUTHENTICATED_RATE_LIMIT)
async def list_users(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    page: int = Query(default=1, ge=1),  # mínimo página 1
    page_size: int = Query(default=10, ge=1, le=100),  # entre 1 y 100 registros
    is_active: bool | None = Query(default=None),  # True/False/None (todos)
    role: str | None = Query(default=None),  # filtro por rol
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # solo Admin+ puede listar usuarios
) -> UserPaginated:
    """
    Lista usuarios con paginación y filtros opcionales.

    GET /api/v1/users?page=1&page_size=10
    GET /api/v1/users?is_active=true&role=Empleado
    GET /api/v1/users?is_active=false   ← ver usuarios desactivados
    Requiere: JWT con rol Administrador o Superadmin

    Filtros opcionales — si no se envían, devuelve todos los registros.
    Se pueden combinar: ?is_active=true&role=Administrador
    """
    return await user_service.list(db, page, page_size, is_active, role)


# ============================================================
# GET /api/v1/users/me — Perfil del usuario logueado
# ============================================================
# IMPORTANTE: esta ruta DEBE estar antes de /{document_id}.
# FastAPI evalúa rutas en orden de declaración. Si /{document_id}
# llegara primero, "/me" sería interpretado como document_id="me"
# y devolvería 404 en vez de entrar a este endpoint.
@router.get("/me", response_model=UserResponse)
@limiter.limit(settings.AUTHENTICATED_RATE_LIMIT)
async def get_me(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Devuelve el perfil del usuario actualmente autenticado.

    GET /api/v1/users/me
    Requiere: JWT válido (cualquier rol)

    ¿Por qué no llama a user_service.get()?
    get_current_user ya hizo la query a la BD para validar el token.
    El objeto `current_user` que nos entrega ya es el usuario completo
    de PostgreSQL — no hay que volver a buscarlo.
    """
    # El JWT ya contiene la identidad — simplemente retornamos el usuario
    return UserResponse.model_validate(current_user)


# ============================================================
# GET /api/v1/users/{document_id} — Obtener un usuario
# ============================================================
@router.get("/{document_id}", response_model=UserResponse)
@limiter.limit(settings.AUTHENTICATED_RATE_LIMIT)
async def get_user(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # solo Admin+ puede ver otros usuarios
) -> UserResponse:
    """
    Devuelve los datos de un usuario específico.

    GET /api/v1/users/1000000001
    Requiere: JWT con rol Administrador o Superadmin

    Para ver el propio perfil sin ser Admin, usar GET /users/me.

    ¿Por qué 404 y no 400 si no existe?
    400 Bad Request → el cliente envió datos malformados
    404 Not Found   → los datos son válidos pero el recurso no existe
    Un document_id bien formado que no está en la BD → 404.
    """
    user = await user_service.get(db, document_id)
    return UserResponse.model_validate(user)


# ============================================================
# POST /api/v1/users — Crear usuario (Admin o Superadmin)
# ============================================================
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_user(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # Admin o Superadmin puede crear usuarios
) -> UserResponse:
    """
    Crea un nuevo usuario en el sistema.

    POST /api/v1/users
    Body: UserCreate (JSON)
    Requiere: JWT con rol Administrador o Superadmin

    HU-018: Admin NO puede crear usuarios con rol Administrador ni Superadmin.
    Solo Superadmin puede crear esos niveles.

    ¿Por qué 201 y no 200?
    200 OK      → éxito, el recurso ya existía
    201 Created → éxito, se creó un nuevo recurso
    POST que crea algo siempre devuelve 201.
    """
    # HU-018: Admin solo puede crear Empleados y Supervisores
    if admin.role == UserRole.ADMIN and data.role in (
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    ):
        raise PermissionDeniedError(
            "Solo Superadmin puede crear usuarios con rol Administrador o Superadmin."
        )

    user = await user_service.create(db, data)
    return UserResponse.model_validate(user)


# ============================================================
# PUT /api/v1/users/{document_id} — Actualizar usuario (Admin o Superadmin)
# ============================================================
@router.put("/{document_id}", response_model=UserResponse)
@limiter.limit("30/minute")
async def update_user(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    document_id: str,
    data: UserUpdateSuperadmin,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """
    Actualiza los datos de un usuario. Solo se modifican los campos enviados.

    PUT /api/v1/users/1000000001
    Body: UserUpdateSuperadmin (los campos que quieres cambiar)
    Requiere: JWT con rol Administrador o Superadmin

    HU-018 — restricciones para el Administrador:
    - No puede modificar usuarios con rol Superadmin.
    - No puede cambiar el rol de alguien a Administrador ni Superadmin.
    - No puede cambiar el email (campo descartado silenciosamente).

    Superadmin puede cambiar el email para corregir errores tipográficos.
    """
    # HU-018: pre-fetch para verificar el rol del usuario objetivo
    target = await user_service.get(db, document_id)

    # Nadie puede cambiar su propio rol — Separation of Duties
    if target.document_id == admin.document_id and data.role is not None and data.role != target.role:
        raise PermissionDeniedError("No puedes cambiar tu propio rol.")

    if admin.role == UserRole.ADMIN:
        if target.role == UserRole.SUPERADMIN:
            raise PermissionDeniedError(
                "Administrador no puede modificar usuarios con rol Superadmin."
            )
        if target.role == UserRole.ADMIN and target.document_id != admin.document_id:
            raise PermissionDeniedError(
                "Administrador no puede modificar otros usuarios con rol Administrador."
            )
        if data.role is not None and data.role in (UserRole.ADMIN, UserRole.SUPERADMIN):
            raise PermissionDeniedError(
                "Administrador no puede promover usuarios a rol Administrador ni Superadmin."
            )
        # Email ignorado para Administrador — reconstruir el payload sin ese campo
        filtered = data.model_dump(exclude_unset=True)
        filtered.pop("email", None)
        data = UserUpdateSuperadmin.model_validate(filtered)

    user = await user_service.update(db, document_id, data)
    return UserResponse.model_validate(user)


# ============================================================
# DELETE /api/v1/users/{document_id}/permanent — Borrado físico (solo Superadmin)
# ============================================================
# IMPORTANTE: esta ruta DEBE ir antes de /{document_id} (soft delete).
# FastAPI evalúa rutas en orden de declaración. Sin esta precaución,
# "/{document_id}" matchearía "1234/permanent" como document_id="1234"
# y nunca entraría a este endpoint.
@router.delete("/{document_id}/permanent", response_model=UserResponse)
@limiter.limit("30/minute")
async def hard_delete_user(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superadmin),
) -> UserResponse:
    """
    Elimina físicamente un usuario inactivo sin actividad registrada.

    DELETE /api/v1/users/{document_id}/permanent
    Requiere: JWT con rol Superadmin

    Condiciones:
    - El usuario debe existir (404 si no).
    - El usuario NO debe tener órdenes ni movimientos de inventario.
      Si tiene → 403 con mensaje: "El usuario tiene actividad registrada…"
    - Los refresh tokens se revocan automáticamente por CASCADE en BD.

    Flujo de doble intención: primero desactivar (DELETE /{id}),
    luego eliminar permanentemente desde la vista de detalle.
    """
    user = await user_service.hard_delete(db, document_id)
    return UserResponse.model_validate(user)


# ============================================================
# DELETE /api/v1/users/{document_id} — Desactivar usuario (Admin o Superadmin)
# ============================================================
@router.delete("/{document_id}", response_model=UserResponse)
@limiter.limit("30/minute")
async def delete_user(
    request: Request,  # requerido por slowapi para leer la IP del cliente
    document_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """
    Desactiva un usuario (soft delete — no borra el registro de la BD).

    DELETE /api/v1/users/1000000001
    Requiere: JWT con rol Administrador o Superadmin

    HU-018: Admin no puede desactivar usuarios Superadmin.

    La respuesta devuelve el usuario con is_active=False,
    confirmando visualmente que fue desactivado.
    """
    target = await user_service.get(db, document_id)

    # Nadie puede desactivar su propia cuenta vía este endpoint
    if admin.document_id == document_id:
        raise PermissionDeniedError(
            "No puedes desactivar tu propia cuenta. Contacta a un Superadmin."
        )

    # Admin no puede desactivar a Superadmin ni a otro Admin
    if admin.role == UserRole.ADMIN and target.role in (UserRole.SUPERADMIN, UserRole.ADMIN):
        raise PermissionDeniedError(
            "Administrador no puede desactivar usuarios con rol igual o superior."
        )

    user = await user_service.delete(db, document_id)
    return UserResponse.model_validate(user)
