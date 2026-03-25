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
#   2. Ejecuta las dependencias: get_db() → get_current_user()
#   3. get_current_user() verifica el JWT → si falla: 401
#   4. Llama al endpoint con db + current_user ya resueltos
#   5. El endpoint delega en user_service → user_service llama al crud
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.user import UserCreate, UserPaginated, UserResponse, UserUpdate
from app.services.user import user_service

# prefix="/users": todas las rutas empiezan con /users
# Combinado con el prefijo del router principal → /api/v1/users
# tags=["users"]: agrupa los endpoints bajo "users" en Swagger (/docs)
router = APIRouter(prefix="/users", tags=["users"])


# ============================================================
# GET /api/v1/users — Listar usuarios (paginado)
# ============================================================
@router.get("/", response_model=UserPaginated)
async def list_users(
    page: int = Query(default=1, ge=1),               # mínimo página 1
    page_size: int = Query(default=10, ge=1, le=100), # entre 1 y 100 registros
    is_active: bool | None = Query(default=None),     # True/False/None (todos)
    role: str | None = Query(default=None),           # 'Administrador'/'Empleado'/None
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),   # cualquier usuario autenticado
) -> UserPaginated:
    """
    Lista usuarios con paginación y filtros opcionales.

    GET /api/v1/users?page=1&page_size=10
    GET /api/v1/users?is_active=true&role=Empleado
    GET /api/v1/users?is_active=false   ← ver usuarios desactivados

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
async def get_me(
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
async def get_user(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Devuelve los datos de un usuario específico.

    GET /api/v1/users/1000000001

    {document_id} en el path es un "path parameter".
    FastAPI lo extrae de la URL y lo pasa como argumento a la función.

    ¿Por qué 404 y no 400 si no existe?
    400 Bad Request → el cliente envió datos malformados
    404 Not Found   → los datos son válidos pero el recurso no existe
    Un document_id bien formado que no está en la BD → 404.
    """
    user = await user_service.get(db, document_id)
    return UserResponse.model_validate(user)


# ============================================================
# POST /api/v1/users — Crear usuario (solo Administrador)
# ============================================================
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # solo Administrador puede crear
) -> UserResponse:
    """
    Crea un nuevo usuario en el sistema.

    POST /api/v1/users
    Body: UserCreate (JSON)
    Requiere: JWT con rol Administrador

    ¿Por qué 201 y no 200?
    200 OK      → éxito, el recurso ya existía
    201 Created → éxito, se creó un nuevo recurso
    POST que crea algo siempre devuelve 201.
    """
    user = await user_service.create(db, data)
    return UserResponse.model_validate(user)


# ============================================================
# PUT /api/v1/users/{document_id} — Actualizar usuario (solo Administrador)
# ============================================================
@router.put("/{document_id}", response_model=UserResponse)
async def update_user(
    document_id: str,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """
    Actualiza los datos de un usuario. Solo se modifican los campos enviados.

    PUT /api/v1/users/1000000001
    Body: UserUpdate (solo los campos que quieres cambiar)
    Requiere: JWT con rol Administrador

    ¿Por qué PUT y no PATCH?
    Técnicamente estamos haciendo PATCH (gracias a exclude_unset en crud):
    el cliente puede enviar solo {"phone": "3001234567"} y solo eso cambia.
    En APIs simples se usa PUT para ambos casos — PATCH es más correcto
    semánticamente pero menos común en proyectos pequeños.
    """
    user = await user_service.update(db, document_id, data)
    return UserResponse.model_validate(user)


# ============================================================
# DELETE /api/v1/users/{document_id} — Desactivar usuario (solo Administrador)
# ============================================================
@router.delete("/{document_id}", response_model=UserResponse)
async def delete_user(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """
    Desactiva un usuario (soft delete — no borra el registro de la BD).

    DELETE /api/v1/users/1000000001
    Requiere: JWT con rol Administrador

    La respuesta devuelve el usuario con is_active=False,
    confirmando visualmente que fue desactivado.

    ¿Por qué devolver el usuario y no 204 No Content?
    204 no tiene cuerpo — el cliente no sabe qué fue desactivado.
    Con el objeto devuelto, el frontend puede mostrar:
    "Usuario Juan Pérez (1000000001) fue desactivado."
    Eso es mejor UX en una aplicación de gestión.
    """
    user = await user_service.delete(db, document_id)
    return UserResponse.model_validate(user)
