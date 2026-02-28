# ============================================================
# BizCore — Modelo SQLAlchemy: tabla `inventory_movements`
# ============================================================
#
# ¿QUÉ ES ESTO?
# La representación Python de la tabla `inventory_movements`.
# Cada fila registra UN movimiento de inventario: cuántas unidades
# de qué producto se movieron, de qué tipo, quién lo hizo y cuándo.
#
# ¿POR QUÉ UNA TABLA SEPARADA Y NO SOLO `product.stock`?
# La columna `product.stock` guarda el saldo actual (cuánto hay HOY).
# Esta tabla guarda el historial (qué pasó y cuándo).
# ANALOGÍA: product.stock = saldo de tu cuenta bancaria.
#           inventory_movements = el extracto completo de transacciones.
#
# ¿CUÁNDO SE CREA UNA FILA AQUÍ?
# Cada vez que alguien hace:
#   - ENTRADA: recibió mercancía (stock sube)
#   - SALIDA:  despachó mercancía (stock baja)
#   - AJUSTE:  corrigió el stock tras un conteo físico (stock se fija)
#
# ¿QUIÉN ACTUALIZA `product.stock`?
# La capa de servicios (services/inventory.py). Cuando se registra
# un movimiento, el servicio: 1) crea la fila aquí, 2) actualiza stock.
# El modelo no hace eso — solo describe la estructura de la tabla.
#
# ============================================================

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryMovement(Base):
    """
    Tabla `inventory_movements` en PostgreSQL.

    Cada instancia representa un movimiento de inventario registrado.
    """

    __tablename__ = "inventory_movements"

    # ----------------------------------------------------------
    # Clave primaria autoincremental
    #
    # Igual que Product: los movimientos no tienen un identificador
    # natural, les asignamos uno nosotros.
    # ----------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------
    # FK al producto afectado
    #
    # ForeignKey("products.id"): enlaza esta columna con la PK
    # de la tabla `products`. SQLAlchemy usará esto para JOIN,
    # y PostgreSQL lo usará para garantizar integridad referencial
    # (no puedes registrar un movimiento de un producto que no existe).
    #
    # ondelete="RESTRICT": si alguien intenta BORRAR un producto
    # que ya tiene movimientos registrados, PostgreSQL lo rechaza.
    # Tiene sentido: no deberías poder borrar un producto con historial.
    # En nuestro sistema hacemos soft delete (is_active=False), así que
    # este RESTRICT es una red de seguridad extra, nunca debería activarse.
    # ----------------------------------------------------------
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ----------------------------------------------------------
    # Tipo de movimiento
    #
    # Valores válidos (se validan en el schema Pydantic, no aquí):
    #   "ENTRADA" → mercancía recibida      → product.stock += quantity
    #   "SALIDA"  → mercancía despachada    → product.stock -= quantity
    #   "AJUSTE"  → corrección por conteo   → product.stock  = quantity
    #
    # ¿Por qué String y no un Enum de Python?
    # Consistencia con el resto del proyecto (User.role también es String).
    # La validación de valores permitidos la hace Pydantic en el schema.
    # Guardar strings en la BD también facilita la lectura directa de la tabla.
    # ----------------------------------------------------------
    movement_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # ----------------------------------------------------------
    # Cantidad
    #
    # SIEMPRE positivo (≥ 1). La validación ge=1 va en el schema.
    # La DIRECCIÓN del movimiento la determina `movement_type`:
    #   - ENTRADA/SALIDA: cuántas unidades entran o salen
    #   - AJUSTE: el valor absoluto al que debe quedar el stock
    #
    # ¿Por qué no negativo para SALIDA?
    # Mantener la cantidad siempre positiva hace los reportes más
    # claros: sumas de ENTRADA vs sumas de SALIDA, sin confusión
    # de signos. El tipo ya dice la dirección.
    # ----------------------------------------------------------
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # ----------------------------------------------------------
    # Notas opcionales
    #
    # El usuario puede agregar contexto: "compra proveedor XYZ",
    # "venta factura #123", "conteo físico mensual", etc.
    # nullable=True: no es obligatorio justificar cada movimiento.
    # ----------------------------------------------------------
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # ----------------------------------------------------------
    # FK al usuario que registró el movimiento
    #
    # ¿Por qué String(20) y no Integer?
    # Porque la PK de `users` es `document_id` (cédula), un String.
    # La FK debe tener el MISMO tipo que la columna a la que apunta.
    #
    # nullable=True: si el usuario que creó el movimiento es eliminado
    # (en teoría, nosotros hacemos soft delete, pero por precaución)
    # el movimiento histórico queda con created_by_id = NULL en vez
    # de fallar. ondelete="SET NULL" le dice a PostgreSQL que haga
    # esto automáticamente si se borra el usuario referenciado.
    #
    # Así el historial de inventario nunca se rompe por cambios en usuarios.
    # ----------------------------------------------------------
    created_by_id: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.document_id", ondelete="SET NULL"),
        nullable=True,
    )

    # ----------------------------------------------------------
    # Timestamp de creación
    #
    # server_default=func.now(): PostgreSQL registra el momento exacto
    # del INSERT en el servidor de BD. No hay campo `updated_at` porque
    # los movimientos de inventario son INMUTABLES — no se editan,
    # solo se crean. Si hay un error, se crea un movimiento corrector.
    # ----------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
