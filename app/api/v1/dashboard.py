# ============================================================
# BizCore — Endpoint para Dashboard
# ============================================================
#
# ANALOGÍA: este archivo es el mesero más sencillo del sistema.
# Los otros meseros (products, orders, etc.) tienen varios platos
# en el menú. Este mesero solo sirve uno: el tablero del dueño.
#
# Su trabajo es mínimo:
#   1. Verificar que el cliente trae su credencial (JWT)
#   2. Pedirle el reporte al asistente (services/dashboard.py)
#   3. Entregárselo al cliente
#
# No calcula nada, no valida reglas de negocio, no coordina tablas.
# Toda la lógica vive en el servicio — el endpoint solo conecta
# la petición HTTP con ese servicio.
#
# ¿POR QUÉ CUALQUIER ROL PUEDE VER EL DASHBOARD?
# En este negocio, tanto el Administrador como el Empleado necesitan
# ver el estado del inventario y los pedidos para hacer su trabajo.
# Restringirlo solo al Admin sería más restrictivo de lo necesario.
# No hay datos sensibles aquí — son métricas del negocio, no datos
# personales ni financieros individuales.
#
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard as dashboard_service

# prefix="/dashboard": todas las rutas empiezan con /dashboard
# Combinado con el prefijo del router principal → /api/v1/dashboard
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============================================================
# GET /api/v1/dashboard/summary — Resumen del negocio
# ============================================================
@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    """
    Devuelve las métricas de negocio en tiempo real.

    GET /api/v1/dashboard/summary
    Requiere: JWT válido (cualquier rol — Administrador o Empleado)

    Respuesta incluye:
    - total_active_users     → usuarios con is_active=True
    - total_active_products  → productos con is_active=True
    - total_stock            → suma de stock de productos activos
    - total_inventory_value  → suma de stock × price de productos activos
    - orders_by_status       → conteo de pedidos por estado
    - low_stock_products     → productos activos con stock < 10

    ¿Por qué el endpoint no tiene lógica propia?
    Toda la lógica de agregación vive en services/dashboard.py.
    El endpoint solo verifica el JWT y delega al servicio.
    Esto permite reutilizar las métricas desde otro contexto
    (una tarea programada, un email diario) sin duplicar código.

    ¿Por qué `current_user` está en la firma aunque no lo usamos?
    Porque `Depends(get_current_user)` tiene un efecto secundario:
    verifica que el token JWT sea válido. Si no hay token o es
    inválido, FastAPI devuelve 401 automáticamente ANTES de
    ejecutar el cuerpo de la función. Sin esta línea, el endpoint
    sería público — cualquiera podría ver las métricas sin autenticarse.
    """
    return await dashboard_service.get_dashboard_summary(db)
