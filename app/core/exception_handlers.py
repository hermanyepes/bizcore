# ============================================================
# BizCore — Manejadores globales de excepciones de dominio
# ============================================================
#
# ANALOGÍA: este es el "sistema central de alarmas".
# Cada función aquí escucha UN tipo de alarma (excepción de dominio)
# y sabe exactamente cómo traducirla en una respuesta HTTP estándar.
#
# REGISTRO: en main.py con app.add_exception_handler(TipoExc, handler).
# FastAPI intercepta la excepción ANTES de devolver la respuesta
# al cliente — el endpoint no necesita try/except.
#
# FORMATO DE RESPUESTA:
#   {
#     "error":  "not_found"       ← código máquina (para el frontend)
#     "detail": "Producto '42' no encontrado"  ← mensaje legible
#   }
#
#   "error"  → string constante que el frontend puede comparar
#               sin depender del texto exacto del mensaje.
#   "detail" → mensaje legible para el usuario.
#
# ¿POR QUÉ NO SOLO USAR "detail"?
#   FastAPI usa {"detail": "..."} para sus propios errores (422, 401).
#   Agregar "error" como clave adicional permite al frontend distinguir
#   entre errores nuestros y errores del framework, sin romper
#   la compatibilidad con los tests que ya verifican ["detail"].
#
# ============================================================

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AlreadyExistsError,
    InactiveResourceError,
    InsufficientStockError,
    NotFoundError,
)


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Traduce NotFoundError → HTTP 404 Not Found."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "detail": str(exc),
        },
    )


async def already_exists_handler(request: Request, exc: AlreadyExistsError) -> JSONResponse:
    """Traduce AlreadyExistsError → HTTP 409 Conflict."""
    return JSONResponse(
        status_code=409,
        content={
            "error": "already_exists",
            "detail": str(exc),
        },
    )


async def inactive_resource_handler(
    request: Request, exc: InactiveResourceError
) -> JSONResponse:
    """Traduce InactiveResourceError → HTTP 400 Bad Request."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "inactive_resource",
            "detail": str(exc),
        },
    )


async def insufficient_stock_handler(
    request: Request, exc: InsufficientStockError
) -> JSONResponse:
    """Traduce InsufficientStockError → HTTP 400 Bad Request."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "insufficient_stock",
            "detail": str(exc),
        },
    )
