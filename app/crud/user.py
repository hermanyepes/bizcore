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
    is_active: bool | None = None,
    role: str | None = None,
) -> tuple[list[User], int]:
    """
    Devuelve una página de usuarios + el total de registros.

    Filtros opcionales:
    - is_active: True → solo activos, False → solo inactivos, None → todos
    - role: 'Administrador' | 'Empleado' | None → todos los roles

    ¿Por qué None como default y no True?
    El admin necesita ver también los usuarios desactivados para
    gestionar el sistema. El frontend decide qué mostrar según el contexto.

    ¿Cómo funcionan los filtros opcionales en SQLAlchemy?
    Construimos la query base y solo añadimos .where() si el parámetro
    no es None. Así la misma función sirve para "sin filtro" y "con filtro".
    """
    # Construir la query base — sin filtros aún
    base_query = select(User)
    count_query = select(func.count()).select_from(User)

    # Aplicar filtros opcionales — solo si el cliente los envió
    if is_active is not None:
        base_query = base_query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)
    if role is not None:
        base_query = base_query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    # Query 1: los usuarios de esta página
    users_result = await db.execute(base_query.offset(skip).limit(limit))
    users = list(users_result.scalars().all())

    # Query 2: el total (con los mismos filtros, sin limit/offset)
    count_result = await db.execute(count_query)
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
