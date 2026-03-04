# ============================================================
# BizCore — Endpoints de autenticación
# ============================================================
#
# ANALOGÍA: este archivo es el portero + la taquilla del restaurante.
#
# POST /auth/login   → el portero te verifica y te da DOS carnets:
#                      uno de 15 min (access) y uno de 7 días (refresh)
#
# POST /auth/refresh → la taquilla: cambias tu carnet vencido por uno
#                      nuevo SIN hacer fila de nuevo (sin contraseña).
#                      Tu tarjeta de cliente frecuente (refresh token)
#                      también se renueva — la anterior queda inválida.
#                      (Esto se llama "rotación de tokens")
#
# POST /auth/logout  → devuelves tu tarjeta de cliente frecuente.
#                      La taquilla la cancela. El carnet de 15 min
#                      expirará solo — no hay forma de "matar" un JWT.
#
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.crud.refresh_token import (
    create_refresh_token_db,
    get_valid_refresh_token,
    revoke_refresh_token,
)
from app.crud.user import get_user_by_email
from app.dependencies import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)

# APIRouter es como un "mini-app" que agrupa endpoints relacionados.
# prefix: todas las rutas de este router empiezan con /auth
# tags: etiqueta que aparece en la documentación de Swagger (/docs)
router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================
# POST /auth/login
# ============================================================

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,        # requerido por slowapi para leer la IP del cliente
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Autentica un usuario y devuelve access token + refresh token.

    POST /api/v1/auth/login
    Body: {"email": "herman@gmail.com", "password": "MiContraseña123"}

    ¿Por qué el mismo error para "email no existe" y "contraseña incorrecta"?
    Seguridad por ambigüedad: un atacante no puede saber si el email existe.
    """
    # Mensaje genérico — nunca revelar si el email existe o no
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Paso 1: buscar el usuario por email
    user = await get_user_by_email(db, data.email)
    if user is None:
        raise invalid_credentials

    # Paso 2: verificar la contraseña
    if not verify_password(data.password, user.password_hash or ""):
        raise invalid_credentials

    # Paso 3: verificar que el usuario esté activo
    # 403 aquí (no 401) porque sí sabemos quién es — pero no puede entrar.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo. Contacta al administrador.",
        )

    # Paso 4: crear access token (JWT, 15 min)
    # "sub" (subject) es el estándar JWT para identificar al usuario.
    access_token = create_access_token(
        data={"sub": user.document_id, "role": user.role}
    )

    # Paso 5: crear refresh token (string aleatorio, 7 días)
    # create_refresh_token() genera el string raw que el cliente guardará.
    # create_refresh_token_db() guarda SHA256(raw) en la BD.
    raw_refresh = create_refresh_token()
    await create_refresh_token_db(db, user_id=user.document_id, raw_token=raw_refresh)

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


# ============================================================
# POST /auth/refresh
# ============================================================

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Renueva el access token usando el refresh token.

    POST /api/v1/auth/refresh
    Body: {"refresh_token": "kP3mN9vRqX2yTzW8..."}

    ROTACIÓN: el token recibido se revoca y se emite uno nuevo.
    El cliente DEBE guardar el nuevo refresh_token de la respuesta.

    ¿Por qué 20/minute y no 5 como en login?
    El refresh token ya es un secreto de 256 bits — no hay riesgo
    de fuerza bruta. El límite de 20 evita abuso sin afectar a
    usuarios legítimos con múltiples pestañas abiertas.
    """
    # Error genérico para todos los casos de token inválido.
    # Igual que en login: nunca revelamos exactamente qué falló.
    invalid_token = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Paso 1: buscar el token en BD (valida hash, is_revoked, expires_at)
    stored_token = await get_valid_refresh_token(db, data.refresh_token)
    if stored_token is None:
        raise invalid_token

    # Paso 2: verificar que el usuario siga activo
    # El usuario pudo haber sido desactivado DESPUÉS de obtener el token.
    result = await db.execute(
        select(User).where(User.document_id == stored_token.user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        # Revocar el token aunque el usuario esté inactivo — limpieza
        await revoke_refresh_token(db, stored_token)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo. Contacta al administrador.",
        )

    # Paso 3: ROTACIÓN — revocar el token antiguo
    # A partir de este momento, si alguien intentara usar el token
    # anterior de nuevo, recibiría 401. Eso indica posible robo.
    await revoke_refresh_token(db, stored_token)

    # Paso 4: emitir nuevos tokens
    new_access_token = create_access_token(
        data={"sub": user.document_id, "role": user.role}
    )
    new_raw_refresh = create_refresh_token()
    await create_refresh_token_db(db, user_id=user.document_id, raw_token=new_raw_refresh)

    return TokenResponse(access_token=new_access_token, refresh_token=new_raw_refresh)


# ============================================================
# POST /auth/logout
# ============================================================

@router.post("/logout", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def logout(
    request: Request,
    data: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Cierra la sesión revocando el refresh token.

    POST /api/v1/auth/logout
    Body: {"refresh_token": "kP3mN9vRqX2yTzW8..."}

    ¿Por qué no se requiere el access token para hacer logout?
    El access token expira solo en máximo 15 minutos.
    La sesión REAL es el refresh token — ese es el que hay que revocar.
    Exigir el access token para logout sería circular: si ya expiró,
    el usuario no podría cerrar sesión.

    ¿Qué pasa con el access token después del logout?
    Sigue siendo válido por lo que queda de sus 15 minutos.
    En producción, un sistema de revocación de JWT (blacklist o Redis)
    podría invalidarlo también. Para este proyecto, el tradeoff es
    aceptable: la ventana de riesgo máxima es 15 minutos.
    """
    # Buscar el token en BD
    stored_token = await get_valid_refresh_token(db, data.refresh_token)

    # Si el token no existe o ya está revocado, devolvemos 401.
    # ¿Podríamos devolver 200 silenciosamente? Algunos sistemas lo hacen
    # (idempotent logout). Aquí preferimos 401 para detectar tokens inválidos.
    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o ya expirado",
        )

    # Revocar el token — la sesión queda cerrada
    await revoke_refresh_token(db, stored_token)

    return {"message": "Sesión cerrada exitosamente"}
