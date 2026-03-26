# ============================================================
# BizCore — CRUD: operaciones de BD para AuditLog
# ============================================================
#
# ANALOGÍA: este archivo es el escribano del sistema.
# Su único trabajo es recibir los datos de una acción
# y dejar constancia permanente en la BD.
#
# ¿POR QUÉ SOLO UNA FUNCIÓN?
# Un registro de auditoría es inmutable por definición.
# Solo se crea — nunca se lee desde aquí, nunca se modifica,
# nunca se elimina. Si en el futuro se necesita consultar logs,
# se agrega una función get() separada en ese momento.
#
# ============================================================

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log(
    db: AsyncSession,
    user_id: str,
    action: str,
    resource: str,
    resource_id: str,
    changes: dict | None = None,
) -> None:
    """
    Inserta un registro de auditoría en la BD.

    Parámetros:
        db          — sesión activa de base de datos
        user_id     — document_id del usuario que ejecutó la acción
        action      — "create" | "update" | "delete"
        resource    — módulo afectado: "user" | "product" | "order" | ...
        resource_id — ID del objeto afectado, siempre como string
        changes     — dict con antes/después (solo en "update"), o None

    ¿Por qué devuelve None y no el objeto creado?
    El servicio que llama esta función no necesita el log de vuelta.
    Su única responsabilidad es dejar el registro — no procesar
    el resultado. Devolver None comunica esa intención claramente.

    ¿Por qué no hay await db.refresh() al final?
    db.refresh() sirve para recargar el objeto con datos que la BD
    generó automáticamente (ej: el id autoincremental o el timestamp).
    Como no devolvemos el objeto, no necesitamos recargarlo.
    """
    # Construir el objeto AuditLog con los datos recibidos.
    # SQLAlchemy no lo guarda aún — solo existe en memoria.
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        changes=changes,
    )

    # Agregar el objeto a la sesión activa.
    # db.add() le dice a SQLAlchemy: "cuando hagas commit,
    # incluye este INSERT en la transacción".
    db.add(entry)

    # Confirmar la transacción — ejecuta el INSERT en PostgreSQL.
    # El timestamp lo asigna PostgreSQL automáticamente (server_default).
    await db.commit()
