# ============================================================
# BizCore — Endpoints CRUD para usuarios
# ============================================================
#
# ANALOGÍA: este archivo son los meseros de BizCore.
# Reciben pedidos (HTTP requests), hablan con el guardabodega
# (crud/user.py), y entregan el resultado al cliente (response).
#
# Los meseros NO saben cómo funciona la BD — solo saben:
#   - Qué pedido llegó (parámetros de la request)
#   - Si el cliente tiene carnet (JWT validado por Depends)
#   - Qué traer del guardabodega (llaman a crud)
#   - Cómo presentar el plato (response_model filtra los datos)
#
# FLUJO DE UNA REQUEST TÍPICA:
#   1. FastAPI recibe GET /api/v1/users/1000000001
#   2. Ejecuta las dependencias: get_db() → get_current_user()
#   3. get_current_user() verifica el JWT → si falla: 401
#   4. Llama al endpoint con db + current_user ya resueltos
#   5. El endpoint llama a crud → crud habla con PostgreSQL
#   6. FastAPI serializa la respuesta con response_model
#
# ============================================================

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import user as user_crud
from app.dependencies import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.user import UserCreate, UserPaginated, UserResponse, UserUpdate

# prefix="/users": todas las rutas empiezan con /users
# Combinado con el prefijo del router principal → /api/v1/users
# tags=["users"]: agrupa los endpoints bajo "users" en Swagger (/docs)
router = APIRouter(prefix="/users", tags=["users"])


# ============================================================
# GET /api/v1/users — Listar usuarios (paginado)
# ============================================================
@router.get("/", response_model=UserPaginated)
async def list_users(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # cualquier usuario autenticado
) -> UserPaginated:
    """
    Lista todos los usuarios con paginación.

    GET /api/v1/users?page=1&page_size=10

    ¿Qué son los query parameters?
    Son los parámetros después del ? en la URL.
    FastAPI los mapea automáticamente a los argumentos de la función
    cuando el argumento NO está en el path (/{algo}).

    ¿Por qué `current_user` está aquí si no lo usamos?
    Porque Depends(get_current_user) tiene dos efectos:
    1. Verifica el JWT y lanza 401 si es inválido/ausente
    2. Devuelve el usuario — aquí no lo necesitamos,
       pero declarar el Depends es suficiente para proteger el endpoint.
    """
    # Convertir page/page_size a skip/limit (los parámetros nativos de SQL)
    # Ejemplo: page=2, page_size=10 → skip=10 (saltar los primeros 10)
    skip = (page - 1) * page_size

    users, total = await user_crud.get_users(db, skip=skip, limit=page_size)

    # math.ceil redondea hacia arriba: 11 usuarios / 10 por página = 2 páginas
    pages = math.ceil(total / page_size) if total > 0 else 0

    return UserPaginated(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


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
    user = await user_crud.get_user_by_id(db, document_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario con document_id '{document_id}' no encontrado",
        )
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

    ¿Por qué verificar duplicados antes de llamar a create_user?
    Si no lo hacemos, PostgreSQL lanzará un IntegrityError (UNIQUE violation).
    FastAPI lo convertiría en un 500 Internal Server Error genérico.
    Es mejor capturarlo y devolver un 409 Conflict con un mensaje claro.
    """
    # Verificar que no exista ya un usuario con ese email
    existing_email = await user_crud.get_user_by_email(db, data.email)
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con el email '{data.email}'",
        )

    # Verificar que no exista ya un usuario con ese document_id
    existing_id = await user_crud.get_user_by_id(db, data.document_id)
    if existing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con document_id '{data.document_id}'",
        )

    user = await user_crud.create_user(db, data)
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
    user = await user_crud.update_user(db, document_id, data)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario con document_id '{document_id}' no encontrado",
        )
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
    user = await user_crud.delete_user(db, document_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario con document_id '{document_id}' no encontrado",
        )
    return UserResponse.model_validate(user)
