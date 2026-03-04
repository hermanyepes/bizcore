# ============================================================
# BizCore — Modelo SQLAlchemy: tabla `suppliers`
# ============================================================
#
# ¿QUÉ ES ESTO?
# La representación Python de la tabla `suppliers` en PostgreSQL.
# Cada instancia de esta clase = una fila = un proveedor registrado.
#
# ¿POR QUÉ NO TIENE RELACIONES (FKs) TODAVÍA?
# En esta fase, Supplier vive solo. En Phase 5 (Orders), los pedidos
# tendrán una FK que apunta aquí. Por ahora no la definimos para
# no añadir complejidad que aún no necesitamos.
#
# ============================================================

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Supplier(Base):
    """
    Tabla `suppliers` en PostgreSQL.

    Representa a las empresas o personas que nos venden productos.
    """

    __tablename__ = "suppliers"

    # ----------------------------------------------------------
    # Clave primaria autoincremental
    #
    # Igual que Product: los proveedores no tienen un identificador
    # natural universal, así que generamos uno nosotros.
    # PostgreSQL asigna 1, 2, 3... automáticamente en cada INSERT.
    # ----------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------
    # Nombre — obligatorio y único
    #
    # No pueden existir dos proveedores con el mismo nombre.
    # Es el identificador de negocio: cuando alguien dice
    # "Distribuidora El Maíz", debe haber exactamente uno.
    # nullable=False: el nombre siempre debe venir en el request.
    # ----------------------------------------------------------
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)

    # ----------------------------------------------------------
    # Email de contacto — opcional, pero único si se provee
    #
    # nullable=True: algunos proveedores se contactan solo por teléfono.
    # unique=True: si se provee un email, no puede repetirse.
    #
    # ¿Cómo puede ser nullable=True Y unique=True al mismo tiempo?
    # En SQL, NULL no es igual a NULL (NULL ≠ NULL).
    # Por eso se permiten múltiples filas con NULL en una columna
    # UNIQUE — no se considera duplicado.
    # Si alguien registra un email concreto, ese sí debe ser único.
    # ----------------------------------------------------------
    contact_email: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )

    # ----------------------------------------------------------
    # Teléfono y dirección — puramente opcionales
    #
    # phone: String(20) es suficiente para cualquier formato:
    # "+57 310 555 1234", "(601) 555-0000", etc.
    # No usamos Integer porque los teléfonos no son números
    # matemáticos — nadie los suma ni los resta.
    #
    # address: dónde están sus bodegas, para coordinar entregas.
    # ----------------------------------------------------------
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ----------------------------------------------------------
    # Soft delete + auditoría — mismo patrón que User y Product
    #
    # is_active=False en vez de DELETE: el historial queda intacto.
    # Si en Phase 5 un pedido referencia este proveedor, la fila
    # sigue existiendo aunque el proveedor esté "desactivado".
    #
    # created_at: server_default=func.now() → PostgreSQL pone la
    # fecha/hora del servidor en el momento del INSERT.
    # ----------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # ----------------------------------------------------------
    # Última modificación — mismo patrón que User y Product
    #
    # onupdate=func.now(): se llena automáticamente en cada UPDATE.
    # nullable=True: NULL hasta el primer PUT sobre este proveedor.
    # ----------------------------------------------------------
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
