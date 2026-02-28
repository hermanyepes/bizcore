# ============================================================
# BizCore — Modelo SQLAlchemy: tabla `products`
# ============================================================
#
# ¿QUÉ ES ESTO?
# La representación Python de la tabla `products` en PostgreSQL.
# SQLAlchemy lee esta clase y sabe cómo crear la tabla, insertar
# filas, consultarlas y actualizarlas.
#
# ¿DIFERENCIA CON LOS SCHEMAS PYDANTIC?
# Este modelo = estructura interna (BD). Incluye TODOS los campos.
# Los schemas = forma de los datos en la API (entrada y salida).
#
# ¿POR QUÉ Mapped[str] en vez de Column(String)?
# SQLAlchemy 2.0 introdujo el estilo "mapped" con type hints de Python.
# Ventaja: el editor sabe que `product.name` es un `str`,
# no un objeto genérico. Menos errores, mejor autocompletado.
#
# ============================================================

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    """
    Tabla `products` en PostgreSQL.

    Cada instancia de esta clase representa una fila en la tabla.
    """

    __tablename__ = "products"

    # ----------------------------------------------------------
    # Clave primaria autoincremental
    #
    # A diferencia de User (donde el documento ES el ID),
    # los productos usan un entero autoincremental.
    # ¿Por qué? Porque los productos no tienen un identificador
    # natural único en el mundo real — les asignamos uno nosotros.
    # autoincrement=True: PostgreSQL genera el número automáticamente
    # (1, 2, 3...) cada vez que se inserta un producto nuevo.
    # ----------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------
    # Datos del producto
    #
    # name: único porque no pueden existir dos productos con el
    # mismo nombre en el catálogo. Es un identificador de negocio.
    #
    # description: opcional (nullable). No todo producto necesita
    # una descripción larga.
    # ----------------------------------------------------------
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ----------------------------------------------------------
    # Precio — por qué Integer y no Float o Numeric
    #
    # El peso colombiano (COP) no maneja centavos en la práctica.
    # Un precio real es $15.900, no $15.900,50.
    # Usar Integer es más honesto con el dominio del negocio:
    # evita decimales que nunca van a existir y simplifica
    # las operaciones matemáticas (sumas, totales, reportes).
    # ----------------------------------------------------------
    price: Mapped[int] = mapped_column(Integer, nullable=False)

    # ----------------------------------------------------------
    # Stock — cantidad disponible en bodega
    #
    # default=0: si no se especifica al crear, empieza en cero.
    # Nota: `default` aquí lo maneja Python/SQLAlchemy en el momento
    # del INSERT, no PostgreSQL directamente (a diferencia de
    # server_default que lo maneja el servidor de BD).
    # ----------------------------------------------------------
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ----------------------------------------------------------
    # Categoría — opcional
    #
    # Guardamos la categoría como string libre en vez de una tabla
    # separada. Decisión de simplicidad para esta fase del proyecto.
    # En un sistema más grande, sería una FK a una tabla `categories`.
    # ----------------------------------------------------------
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # ----------------------------------------------------------
    # Soft delete + auditoría
    #
    # is_active: en vez de borrar el producto de la BD, lo marcamos
    # como inactivo. Ventaja: historial conservado, posibilidad de
    # restaurar, no se rompen registros históricos de ventas.
    #
    # created_at: server_default=func.now() le dice a PostgreSQL
    # que genere la fecha/hora automáticamente al insertar.
    # Usamos el reloj del servidor de BD, no el de la aplicación.
    # ----------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
