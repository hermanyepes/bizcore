# ============================================================
# BizCore — Modelo SQLAlchemy: tabla `audit_logs`
# ============================================================
#
# ¿QUÉ ES ESTO?
# La representación Python de la tabla de auditoría en PostgreSQL.
# Cada fila = una acción que alguien hizo sobre los datos del sistema.
#
# ¿POR QUÉ UNA TABLA Y NO UN ARCHIVO .log?
# Un archivo .log es para el técnico (¿el sistema funciona?).
# Esta tabla es para el dueño del negocio (¿quién tocó mis datos?).
# La BD garantiza que los registros no se borren accidentalmente,
# son consultables con filtros (por usuario, por fecha, por módulo),
# y sobreviven reinicios del servidor.
#
# ¿POR QUÉ NO HAY updated_at NI is_active?
# Un registro de auditoría jamás se modifica ni se desactiva.
# Si algo pasó, quedó registrado para siempre. Inmutable por diseño.
#
# ============================================================

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """
    Tabla `audit_logs` en PostgreSQL.

    Cada fila representa una acción de escritura (create / update / delete)
    realizada por un usuario autenticado sobre cualquier módulo del sistema.
    """

    __tablename__ = "audit_logs"

    # ----------------------------------------------------------
    # Clave primaria — autoincremental
    #
    # ¿Por qué int y no str como en User?
    # No hay un identificador de negocio natural para un log.
    # Un número autoincremental es lo más simple y eficiente
    # para una tabla que puede crecer a millones de filas.
    # ----------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------
    # ¿Quién hizo la acción?
    #
    # FK hacia users.document_id — usamos String(20) porque la PK
    # de nuestra tabla users es VARCHAR (número de documento),
    # no un entero autoincremental.
    #
    # nullable=False: todo log DEBE tener un autor. Si no hay
    # usuario autenticado, no debería poder ejecutarse la acción.
    # ----------------------------------------------------------
    user_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("users.document_id"), nullable=False
    )

    # ----------------------------------------------------------
    # ¿Qué acción se realizó?
    #
    # Solo tres valores posibles: "create" | "update" | "delete"
    # No usamos un Enum de PostgreSQL para mantener la migración
    # simple — la validación del valor se hará en el CRUD.
    # ----------------------------------------------------------
    action: Mapped[str] = mapped_column(String(10), nullable=False)

    # ----------------------------------------------------------
    # ¿Sobre qué módulo?
    #
    # "user" | "product" | "supplier" | "order" | "inventory"
    # Permite filtrar todos los cambios de un módulo específico:
    #   SELECT * FROM audit_logs WHERE resource = 'order'
    # ----------------------------------------------------------
    resource: Mapped[str] = mapped_column(String(30), nullable=False)

    # ----------------------------------------------------------
    # ¿Cuál fue el objeto afectado?
    #
    # String porque los IDs del sistema no son todos enteros:
    # - users.document_id es VARCHAR ("1234567890")
    # - products.id, orders.id son enteros — se convierten a str
    #
    # Guardar como string unifica todos los módulos en una sola
    # columna sin necesidad de múltiples FKs opcionales.
    # ----------------------------------------------------------
    resource_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # ----------------------------------------------------------
    # ¿Qué cambió exactamente?
    #
    # Columna JSON — guarda un diccionario Python directamente.
    # Estructura esperada para "update":
    #   {
    #     "price": {"before": 100, "after": 120},
    #     "name":  {"before": "Arroz", "after": "Arroz Premium"}
    #   }
    # Para "create" y "delete": None (no hay "antes/después").
    #
    # nullable=True: en create/delete no hay cambios que registrar.
    # ----------------------------------------------------------
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ----------------------------------------------------------
    # ¿Cuándo ocurrió?
    #
    # server_default=func.now(): PostgreSQL asigna la fecha en el
    # servidor de BD, no en Python. Más confiable — usa el reloj
    # del servidor de base de datos, no el del servidor de la app.
    #
    # No hay onupdate porque este registro jamás se modifica.
    # ----------------------------------------------------------
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
