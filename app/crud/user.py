# ============================================================
# BizCore — CRUD: operaciones de base de datos para User
# ============================================================
#
# ANALOGÍA: este archivo es el guardabodega.
# Solo habla con PostgreSQL. No valida permisos, no toma
# decisiones de negocio, no sabe si el usuario tiene sesión.
# Solo recibe instrucciones y ejecuta: guarda, trae, actualiza.
#
# Cada función recibe `db` (la sesión de BD) como primer
# parámetro. FastAPI la inyecta automáticamente vía Depends(get_db).
#
# ============================================================

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

# ============================================================
# GET — Consultas de lectura
# ============================================================

async def get_user_by_id(db: AsyncSession, document_id: str) -> User | None:
    """
    Busca un usuario por su número de documento.

    Devuelve el objeto User si existe, None si no.

    ¿Qué hace scalar_one_or_none()?
    - scalar_one()          → devuelve el resultado, lanza error si no hay ninguno
    - scalar_one_or_none()  → devuelve el resultado, devuelve None si no hay ninguno
    Usamos la segunda porque un usuario puede no existir y eso es válido.
    """
    result = await db.execute(
        select(User).where(User.document_id == document_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """
    Busca un usuario por su correo electrónico.

    ¿Para qué sirve esta función?
    Para el login. El cliente envía email + password. Primero
    buscamos el usuario por email, luego verificamos la contraseña.
    Si no existe el email → error. Si existe pero la contraseña
    no coincide → error diferente.
    """
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
) -> tuple[list[User], int]:
    """
    Devuelve una página de usuarios + el total de registros.

    ¿Por qué skip y limit y no page y page_size?
    skip y limit son los parámetros nativos de SQL (OFFSET y LIMIT).
    La conversión de page → skip la hace el endpoint:
        skip = (page - 1) * page_size

    ¿Por qué dos queries y no uno?
    Para saber el total de páginas necesitas saber cuántos usuarios
    hay en total. No puedes saberlo solo con la página actual.
    Son dos preguntas diferentes a la BD:
    1. "Dame los usuarios de esta página" → select con limit/offset
    2. "¿Cuántos usuarios hay en total?" → select count(*)

    Devuelve una tupla: (lista de usuarios, total).
    """
    # Query 1: los usuarios de esta página
    users_result = await db.execute(
        select(User).offset(skip).limit(limit)
    )
    users = list(users_result.scalars().all())

    # Query 2: el total de usuarios en la BD
    count_result = await db.execute(
        select(func.count()).select_from(User)
    )
    total = count_result.scalar_one()

    return users, total


# ============================================================
# CREATE — Inserción
# ============================================================

async def create_user(db: AsyncSession, data: UserCreate) -> User:
    """
    Crea un nuevo usuario en la BD.

    ¿Por qué hasheamos la contraseña aquí y no en el endpoint?
    Porque es el único lugar donde se construye el objeto User.
    Si lo hiciéramos en el endpoint, tendríamos que pasar la
    contraseña hasheada como parámetro separado — más confuso.

    Flujo:
    1. Construimos el objeto User (sin guardar aún)
    2. db.add() lo agrega a la sesión (en memoria)
    3. db.commit() ejecuta el INSERT en PostgreSQL
    4. db.refresh() recarga el objeto desde la BD para obtener
       los valores generados por el servidor (join_date, created_at)
    """
    user = User(
        document_id=data.document_id,
        document_type=data.document_type,
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        city=data.city,
        role=data.role,
        password_hash=hash_password(data.password),
        # join_date y created_at los genera PostgreSQL automáticamente
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ============================================================
# UPDATE — Actualización parcial
# ============================================================

async def update_user(
    db: AsyncSession,
    document_id: str,
    data: UserUpdate,
) -> User | None:
    """
    Actualiza solo los campos que el cliente envió.

    ¿Por qué exclude_unset=True?
    UserUpdate tiene todos los campos como opcionales (None por defecto).
    Si el cliente solo envía {"phone": "3001234567"}, model_dump() sin
    exclude_unset devolvería también full_name=None, city=None, etc.,
    borrando datos que el usuario no quería cambiar.
    exclude_unset=True filtra solo los campos que realmente llegaron.

    ¿Qué hace setattr(user, field, value)?
    Es Python puro. Equivale a: user.phone = "3001234567"
    Pero de forma dinámica, sin saber de antemano qué campo es.
    Sin setattr, tendríamos que escribir un if por cada campo posible.
    """
    user = await get_user_by_id(db, document_id)
    if user is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Si el cliente envió una nueva contraseña, hashearla antes de guardar.
    # Además, el modelo tiene `password_hash`, no `password` — hay que
    # renombrar la clave antes de aplicarla al objeto.
    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


# ============================================================
# DELETE — Soft delete
# ============================================================

async def delete_user(db: AsyncSession, document_id: str) -> User | None:
    """
    Desactiva un usuario (soft delete). No borra el registro.

    ¿Por qué soft delete y no DELETE real?
    - Historial: puedes saber que ese usuario existió
    - Auditoría: si algo salió mal, puedes ver quién hizo qué
    - Recuperación: si fue un error, puedes reactivar el usuario
    - Integridad: si en el futuro hay tablas relacionadas (pedidos,
      facturas), un DELETE real rompería esas relaciones

    En vez de borrar, solo marcamos is_active = False.
    Los endpoints de listado filtrarán usuarios inactivos.
    """
    user = await get_user_by_id(db, document_id)
    if user is None:
        return None

    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user
