# ============================================================
# BizCore — Modelo SQLAlchemy: tabla `refresh_tokens`
# ============================================================
#
# ANALOGÍA: esta tabla es el archivo de tarjetas del parqueadero.
# Guarda CUÁLES "tarjetas de cliente frecuente" existen,
# CUÁNDO vencen, y CUÁLES fueron bloqueadas (revocadas) porque
# el cliente cerró sesión o porque detectamos un intento de robo.
#
# DECISIÓN IMPORTANTE: guardamos SHA256(token), NO el token raw.
# Si alguien roba la BD, solo obtiene hashes de 64 chars.
# SHA256 es una función de un solo sentido — no se puede revertir.
# El token original solo vive en la memoria/almacenamiento del cliente.
#
# ¿Por qué una tabla separada y no un campo en `users`?
# Un usuario puede tener múltiples sesiones activas al mismo tiempo:
# celular + computador del trabajo + computador de la casa.
# Cada sesión tiene su propio refresh token. Una tabla dedicada
# permite revocar solo una sesión sin afectar las demás.
#
# ============================================================

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RefreshToken(Base):
    """
    Tabla `refresh_tokens` en PostgreSQL.

    Cada fila = una sesión de usuario (activa o revocada).
    """

    __tablename__ = "refresh_tokens"

    # ----------------------------------------------------------
    # Clave primaria — UUID generado en Python
    #
    # ¿Por qué UUID y no SERIAL (entero autoincremental)?
    # Un SERIAL revela información: si tu token es id=1042, el
    # atacante sabe que hay 1042 sesiones en el sistema.
    # Un UUID v4 es 128 bits de aleatoriedad — no revela nada.
    #
    # default=lambda: str(uuid.uuid4()): Python genera el UUID
    # ANTES de enviarlo a PostgreSQL. Así funciona en SQLite también
    # (importante para los tests que usan SQLite en memoria).
    # ----------------------------------------------------------
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ----------------------------------------------------------
    # Relación con el usuario
    #
    # ForeignKey("users.document_id"): FK a la PK de `users`.
    # ondelete="CASCADE": si el usuario es eliminado de la BD,
    # sus refresh tokens también se eliminan automáticamente.
    # (BizCore usa soft delete, pero el CASCADE es buena práctica).
    # ----------------------------------------------------------
    user_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("users.document_id", ondelete="CASCADE"),
        nullable=False,
    )

    # ----------------------------------------------------------
    # Hash del token — NUNCA el token en texto plano
    #
    # SHA256 produce un hexdigest de exactamente 64 caracteres.
    # Ejemplo: SHA256("AbCdEf...") → "3a7f9b2c4d1e..."
    #
    # unique=True: dos tokens distintos no pueden tener el mismo hash.
    # index=True: cada /refresh busca por este campo — sin índice
    # sería un full table scan en cada petición autenticada.
    # ----------------------------------------------------------
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # ----------------------------------------------------------
    # Vigencia del token
    #
    # Calculado en Python al crear: datetime.now(UTC) + 7 días.
    # No usamos server_default porque el valor viene de
    # settings.REFRESH_TOKEN_EXPIRE_DAYS, no de PostgreSQL.
    # ----------------------------------------------------------
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ----------------------------------------------------------
    # Estado de revocación
    #
    # False → token activo (puede usarse para renovar el access token)
    # True  → token invalidado (logout voluntario o rotación forzada)
    #
    # ¿Por qué guardar revocados y no borrarlos?
    # Auditoría: podemos saber cuándo cerró sesión cada dispositivo.
    # Detección de robo: si un token ya revocado aparece de nuevo,
    # alguien lo está reutilizando → señal de ataque.
    # (Limpieza periódica de tokens expirados: tarea de mantenimiento)
    # ----------------------------------------------------------
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # ----------------------------------------------------------
    # Auditoría — cuándo fue creada esta sesión
    # ----------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
