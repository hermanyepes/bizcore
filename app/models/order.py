# ============================================================
# BizCore — Modelos SQLAlchemy: tablas `orders` y `order_items`
# ============================================================
#
# ¿POR QUÉ DOS CLASES EN UN SOLO ARCHIVO?
# Order y OrderItem son inseparables conceptualmente:
# un ítem sin pedido no existe; un pedido sin ítems no sirve.
# Mantenerlos juntos hace el código más fácil de navegar.
#
# ANALOGÍA — La factura de supermercado:
#   Order     = el encabezado de la factura
#               (número, fecha, proveedor, quién la hizo)
#   OrderItem = cada línea de la factura
#               (producto X, 3 unidades, $5.000 c/u, subtotal $15.000)
#
# ¿QUÉ ES `relationship()`?
# Una FK (ForeignKey) es solo un número entero en la BD.
# `relationship()` convierte ese número en un objeto Python accesible.
# Después de definirlo, puedes hacer:
#       order.items   → lista de OrderItem (sin escribir JOIN)
#       item.order    → el Order padre (sin escribir JOIN)
# SQLAlchemy traduce eso a SQL por debajo. Es conveniencia pura.
#
# ¿QUÉ ES `cascade="all, delete-orphan"`?
# Si eliminas un Order, sus OrderItems se eliminan automáticamente.
# En la BD: ondelete="CASCADE" en la FK de order_items.
# En Python: cascade="all, delete-orphan" en el relationship().
# Ambos deben estar presentes — trabajan en capas distintas.
#
# ============================================================

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ============================================================
# Clase Order — tabla `orders`
# Representa el encabezado de un pedido de compra.
# ============================================================
class Order(Base):
    """
    Tabla `orders` en PostgreSQL.

    Cada instancia representa un pedido hecho a un proveedor.
    Los productos que incluye ese pedido viven en `order_items`.
    """

    __tablename__ = "orders"

    # ----------------------------------------------------------
    # Clave primaria autoincremental
    # ----------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------
    # FK al proveedor — obligatoria
    #
    # Todo pedido debe tener un proveedor: ¿a quién le compramos?
    # nullable=False: no puede haber un pedido sin proveedor.
    #
    # ondelete="RESTRICT": si alguien intenta BORRAR un proveedor
    # que ya tiene pedidos asociados, PostgreSQL lo bloquea.
    # En nuestro sistema usamos soft delete (is_active=False),
    # así que este RESTRICT es una red de seguridad extra.
    # ----------------------------------------------------------
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ----------------------------------------------------------
    # FK al usuario que creó el pedido
    #
    # ¿Por qué String(20)? Porque la PK de `users` es `document_id`
    # (cédula), que es un VARCHAR. La FK debe tener el mismo tipo
    # que la columna a la que apunta.
    #
    # nullable=True + ondelete="SET NULL": si el usuario que hizo
    # el pedido es desactivado o borrado, el pedido histórico queda
    # con created_by_id = NULL en vez de fallar.
    # El pedido existió — solo perdemos la referencia de quién lo hizo.
    # ----------------------------------------------------------
    created_by_id: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("users.document_id", ondelete="SET NULL"),
        nullable=True,
    )

    # ----------------------------------------------------------
    # Estado del pedido
    #
    # Valores válidos: "PENDIENTE" | "COMPLETADO" | "CANCELADO"
    # La validación de estos valores la hace Pydantic en el schema,
    # no SQLAlchemy aquí. Mismo patrón que `movement_type` en Phase 3.
    #
    # default="PENDIENTE": todo pedido nace en estado PENDIENTE.
    # El default lo maneja Python (default=), no PostgreSQL (server_default=),
    # porque es un valor fijo que no depende del momento del INSERT.
    # ----------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default="PENDIENTE"
    )

    # ----------------------------------------------------------
    # Notas opcionales
    #
    # Contexto libre: "compra mensual", "pedido urgente", etc.
    # nullable=True: no es obligatorio justificar cada pedido.
    # ----------------------------------------------------------
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # ----------------------------------------------------------
    # Timestamp de creación
    #
    # server_default=func.now(): PostgreSQL registra el momento
    # exacto del INSERT. Inmutable — los pedidos no se "re-crean".
    # ----------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ----------------------------------------------------------
    # Relationship: Order → lista de OrderItem
    #
    # Esta línea NO crea ninguna columna en la BD.
    # Es conveniencia Python: order.items devuelve la lista de
    # OrderItem asociados a este Order.
    #
    # back_populates="order": le dice a SQLAlchemy que el lado
    # inverso de esta relación se llama `order` en OrderItem.
    # Ambos lados deben declarar back_populates entre sí.
    #
    # cascade="all, delete-orphan":
    #   - "all": al guardar/actualizar un Order, sus items también
    #   - "delete-orphan": al eliminar un Order, sus items se
    #     eliminan automáticamente (igual que la FK CASCADE en BD)
    # ----------------------------------------------------------
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


# ============================================================
# Clase OrderItem — tabla `order_items`
# Representa una línea de detalle dentro de un pedido.
# ============================================================
class OrderItem(Base):
    """
    Tabla `order_items` en PostgreSQL.

    Cada instancia representa UN producto dentro de UN pedido:
    cuántas unidades se pidieron y a qué precio estaban en ese momento.
    """

    __tablename__ = "order_items"

    # ----------------------------------------------------------
    # Clave primaria autoincremental
    # ----------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------
    # FK al pedido padre — obligatoria
    #
    # ondelete="CASCADE": si el Order padre es eliminado, todos
    # sus OrderItems se eliminan automáticamente en cascada.
    # Un ítem no puede existir sin su pedido — no tendría sentido.
    # ----------------------------------------------------------
    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ----------------------------------------------------------
    # FK al producto — obligatoria
    #
    # ondelete="RESTRICT": no se puede borrar un producto que ya
    # tiene líneas de pedido históricas. Mismo razonamiento que
    # en inventory_movements: el historial debe conservarse.
    # ----------------------------------------------------------
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ----------------------------------------------------------
    # Cantidad pedida
    #
    # Siempre positiva (≥ 1). La validación ge=1 va en el schema.
    # ----------------------------------------------------------
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # ----------------------------------------------------------
    # Precio unitario al momento del pedido — SNAPSHOT
    #
    # ¿Por qué no referenciamos product.price directamente?
    # Porque los precios cambian con el tiempo.
    # Si un producto valía $10.000 cuando se hizo el pedido y hoy
    # vale $12.000, el pedido histórico debe seguir mostrando $10.000.
    #
    # ANALOGÍA: en una factura de papel ya impresa, el precio queda
    # congelado en ese papel para siempre.
    #
    # Este valor lo copia `services/order.py` desde product.price
    # en el momento de crear el pedido. El cliente NO lo envía.
    # ----------------------------------------------------------
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)

    # ----------------------------------------------------------
    # Subtotal = quantity × unit_price
    #
    # Técnicamente es un campo calculado (quantity × unit_price).
    # ¿Por qué guardarlo si se puede calcular?
    # 1. Performance: evita recalcular en cada consulta.
    # 2. Historial: si mañana cambia alguna regla de negocio sobre
    #    cómo calcular el total, los pedidos pasados ya tienen
    #    su subtotal grabado correctamente.
    #
    # `services/order.py` calcula y asigna este valor al crear.
    # ----------------------------------------------------------
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)

    # ----------------------------------------------------------
    # Relationship: OrderItem → Order (lado inverso)
    #
    # back_populates="items": el lado Order llama a esta relación
    # `items`; el lado OrderItem llama a esta relación `order`.
    # ----------------------------------------------------------
    order: Mapped["Order"] = relationship("Order", back_populates="items")
