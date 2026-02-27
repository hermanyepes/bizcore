# ============================================================
# BizCore — Modelo SQLAlchemy: tabla `users`
# ============================================================
#
# ¿QUÉ ES ESTO?
# La representación Python de la tabla `users` en PostgreSQL.
# SQLAlchemy lee esta clase y sabe:
# - Cómo crear la tabla (CREATE TABLE)
# - Cómo insertar, leer, actualizar y eliminar filas
# - Qué columnas existen y qué tipo tienen
#
# ¿DIFERENCIA CON LOS SCHEMAS PYDANTIC?
# Este modelo = estructura interna (BD). Incluye password_hash.
# Los schemas = forma de los datos en la API. Nunca exponen password_hash.
#
# ¿POR QUÉ Mapped[str] en vez de Column(String)?
# SQLAlchemy 2.0 introdujo el estilo "mapped" con type hints de Python.
# Ventaja práctica: el editor sabe que `user.full_name` es un `str`,
# no un objeto genérico. Menos errores, mejor autocompletado.
#
# ============================================================

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """
    Tabla `users` en PostgreSQL.

    Cada instancia de esta clase representa una fila en la tabla.
    """

    __tablename__ = "users"

    # ----------------------------------------------------------
    # Clave primaria
    # Usamos el número de documento como PK.
    # Ventaja: no hay ID autoincremental separado, el documento ES el ID.
    # Desventaja: si el documento cambia, hay que actualizar todas las
    # relaciones. Para este dominio es aceptable.
    # ----------------------------------------------------------
    document_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    # ----------------------------------------------------------
    # Datos personales
    # str | None = puede ser NULL en la BD
    # str (sin None) = NOT NULL obligatorio
    # ----------------------------------------------------------
    document_type: Mapped[str] = mapped_column(String(10), nullable=False)
    full_name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ----------------------------------------------------------
    # Rol de acceso
    # La restricción CHECK ('Administrador' | 'Empleado') se define
    # en la migración de Alembic, no aquí directamente.
    # Aquí solo definimos el tipo y la restricción NOT NULL.
    # ----------------------------------------------------------
    role: Mapped[str] = mapped_column(String(15), nullable=False)

    # ----------------------------------------------------------
    # Autenticación
    # Opcional porque un usuario puede existir sin contraseña aún
    # (ej: creado por admin, aún no ha activado su cuenta).
    # Nunca guardamos la contraseña en texto plano — solo el hash.
    # ----------------------------------------------------------
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ----------------------------------------------------------
    # Auditoría y soft delete
    #
    # server_default=func.now(): PostgreSQL genera el valor por
    # defecto en el servidor, no en Python. Más confiable porque
    # usa el reloj del servidor de BD, no del servidor de la app.
    #
    # is_active = soft delete: en vez de borrar el registro de la BD,
    # lo marcamos como inactivo. Ventaja: historial conservado,
    # posibilidad de restaurar, integridad referencial.
    # ----------------------------------------------------------
    join_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
