# ============================================================
# BizCore — Endpoint de autenticación
# ============================================================
#
# ANALOGÍA: este archivo es el portero del restaurante.
# Solo existe un endpoint: POST /login.
# El portero verifica tu identidad y te da un carnet (JWT).
# Con ese carnet puedes entrar al resto del restaurante.
#
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.crud.user import get_user_by_email
from app.dependencies import get_db
from app.schemas.auth import LoginRequest, TokenResponse

# APIRouter es como un "mini-app" que agrupa endpoints relacionados.
# prefix: todas las rutas de este router empiezan con /auth
# tags: etiqueta que aparece en la documentación de Swagger (/docs)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Autentica un usuario y devuelve un token JWT.

    POST /api/v1/auth/login
    Body: {"email": "herman@gmail.com", "password": "MiContraseña123"}

    ¿Por qué el mismo error para "email no existe" y "contraseña incorrecta"?
    Seguridad. Si diéramos mensajes diferentes, un atacante podría:
    1. Probar emails hasta encontrar uno que exista ("email no encontrado")
    2. Solo entonces intentar contraseñas sobre ese email confirmado
    Con el mismo error, el atacante no sabe si el email existe o no.
    Esta técnica se llama "security through ambiguity" (seguridad por ambigüedad).
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
    # verify_password compara el texto plano con el hash guardado en la BD.
    # Si no coincide, mismo error que "usuario no encontrado".
    if not verify_password(data.password, user.password_hash or ""):
        raise invalid_credentials

    # Paso 3: verificar que el usuario esté activo
    # 403 aquí (no 401) porque sí sabemos quién es — pero no puede entrar.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo. Contacta al administrador.",
        )

    # Paso 4: crear el JWT
    # "sub" (subject) es el estándar JWT para identificar al usuario.
    # Guardamos document_id porque es la PK — con eso podemos buscarlo
    # en la BD en cada petición autenticada.
    access_token = create_access_token(
        data={"sub": user.document_id, "role": user.role}
    )

    return TokenResponse(access_token=access_token)
