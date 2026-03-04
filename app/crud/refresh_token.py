# ============================================================
# BizCore — CRUD: operaciones de BD para RefreshToken
# ============================================================
#
# ANALOGÍA: este archivo es el empleado del archivo de tarjetas
# en el parqueadero. Su único trabajo es:
#   - Emitir una tarjeta nueva (create_refresh_token_db)
#   - Buscar una tarjeta por su huella dactilar (get_valid_refresh_token)
#   - Marcar una tarjeta como bloqueada (revoke_refresh_token)
#
# No toma decisiones de negocio — eso lo hace el endpoint en auth.py.
# Solo habla con la BD.
#
# ============================================================

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_refresh_token
from app.models.refresh_token import RefreshToken


async def create_refresh_token_db(
    db: AsyncSession,
    user_id: str,
    raw_token: str,
) -> RefreshToken:
    """
    Guarda el hash del refresh token en la BD.

    ¿Por qué raw_token como parámetro y no el hash directamente?
    Para que esta función haga el hash internamente — así el endpoint
    no necesita conocer el detalle de implementación del hashing.
    El endpoint solo tiene el token raw (que acaba de generar) y
    lo pasa aquí. Este CRUD hace el SHA256.

    expires_at: calculado desde ahora + REFRESH_TOKEN_EXPIRE_DAYS.
    datetime.now(UTC): siempre UTC para consistencia entre servidores.
    """
    token = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token


async def get_valid_refresh_token(
    db: AsyncSession,
    raw_token: str,
) -> RefreshToken | None:
    """
    Busca un refresh token válido por su hash.

    "Válido" significa que cumple LAS TRES condiciones:
    1. El hash existe en la BD (el token es auténtico)
    2. No está revocado (el usuario no cerró sesión)
    3. No ha expirado (dentro del período de 7 días)

    Si alguna condición falla → devuelve None.
    El endpoint que llama esta función interpreta None como 401.

    ¿Por qué los tres filtros en una sola query y no verificar
    en Python después de traer el registro?
    Eficiencia: una sola consulta con WHERE es mejor que traer
    el registro y luego hacer if-elif en Python. La BD está
    optimizada para filtrar — Python no.
    """
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712 — SQLAlchemy requiere == False
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(
    db: AsyncSession,
    refresh_token: RefreshToken,
) -> None:
    """
    Revoca un refresh token: lo marca como is_revoked=True.

    Recibe el objeto RefreshToken ya cargado (no el raw string).
    El endpoint llama a get_valid_refresh_token primero y pasa
    el resultado aquí — no necesitamos buscarlo de nuevo.

    Después de revocar, este token no puede usarse para /refresh.
    """
    refresh_token.is_revoked = True
    await db.commit()
