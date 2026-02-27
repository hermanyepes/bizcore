# ============================================================
# BizCore — Dependencies: funciones inyectadas por FastAPI
# ============================================================
#
# ¿QUÉ ES "DEPENDENCY INJECTION" EN FASTAPI?
#
# Cuando un endpoint declara un parámetro con `Depends(algo)`,
# FastAPI llama a `algo` automáticamente ANTES de ejecutar el
# endpoint, y pasa el resultado como argumento.
#
# Ejemplo:
#   @router.get("/users")
#   async def list_users(db: AsyncSession = Depends(get_db)):
#       # `db` es una sesión ya abierta, lista para usar
#
# Ventajas:
# 1. El endpoint no sabe cómo se crea la sesión — solo la usa
# 2. FastAPI garantiza que la sesión se cierra al terminar
# 3. En tests, puedes reemplazar `get_db` con una BD de prueba
#    sin cambiar ni una línea del endpoint
#
# ¿POR QUÉ NO simplemente hacer `db = AsyncSessionLocal()` dentro
# del endpoint?
# Porque tendrías que recordar cerrarla manualmente en todos los
# caminos posibles (éxito, error, excepción). `Depends` con `yield`
# garantiza el cierre sin importar cómo termina el endpoint.
#
# ============================================================

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models.user import User

# OAuth2PasswordBearer le dice a FastAPI que el token viene en el
# header `Authorization: Bearer <token>`. Además hace que el
# endpoint aparezca con un candado en Swagger (/docs).
# tokenUrl: la URL donde el cliente obtiene el token (el login).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ============================================================
# get_db — Inyectar sesión de base de datos
# ============================================================
async def get_db() -> AsyncGenerator[AsyncSession]:
    """
    Abre una sesión de BD, la cede al endpoint, y la cierra al terminar.

    ¿Por qué `yield` y no `return`?
    Con `return`, la función termina y no hay forma de ejecutar
    código de limpieza después. Con `yield`, FastAPI:
    1. Ejecuta todo lo que está ANTES del yield (abre la sesión)
    2. Pasa el valor al endpoint
    3. Espera a que el endpoint termine
    4. Ejecuta todo lo que está DESPUÉS del yield (cierra la sesión)

    El bloque `finally` garantiza que la sesión se cierre SIEMPRE,
    incluso si el endpoint lanza una excepción.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ============================================================
# get_current_user — Verificar JWT y devolver usuario activo
# ============================================================
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Verifica el JWT y devuelve el usuario autenticado.

    Pasos:
    1. Extrae el token del header Authorization (oauth2_scheme)
    2. Decodifica y verifica la firma y expiración del JWT
    3. Extrae el `sub` (document_id del usuario) del payload
    4. Busca el usuario en la BD
    5. Verifica que el usuario esté activo (is_active=True)

    Si algo falla en cualquier paso → 401 Unauthorized.
    Si todo está bien → devuelve el objeto User de la BD.

    ¿Por qué 401 y no 403?
    401 = "No sé quién eres" (token inválido/expirado/ausente)
    403 = "Sé quién eres pero no tienes permiso" (rol insuficiente)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Buscar el usuario en la BD por su document_id
    result = await db.execute(select(User).where(User.document_id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )

    return user


# ============================================================
# require_admin — Verificar que el usuario sea Administrador
# ============================================================
def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependencia adicional para endpoints que requieren rol Administrador.

    Uso:
        @router.delete("/{document_id}")
        async def delete_user(admin: User = Depends(require_admin)):
            ...

    Si el usuario es Empleado → 403 Forbidden.
    Si es Administrador → devuelve el usuario (igual que get_current_user).

    ¿Por qué una función separada y no validar el rol dentro de cada endpoint?
    Porque así la lógica de autorización está en un solo lugar.
    Si cambia la regla ("ahora los Empleados también pueden eliminar"),
    cambias una línea aquí y aplica a todos los endpoints automáticamente.
    """
    if current_user.role != "Administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol Administrador para esta operación",
        )
    return current_user
