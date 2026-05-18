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
#   2. Verificar que el rol tiene permiso para ver métricas
#   3. Pedirle el reporte al asistente (services/dashboard.py)
#   4. Entregárselo al cliente
#
# No calcula nada, no valida reglas de negocio, no coordina tablas.
# Toda la lógica vive en el servicio — el endpoint solo conecta
# la petición HTTP con ese servicio.
#
# ¿POR QUÉ SOLO SUPERVISOR EN ADELANTE?
# El dashboard expone métricas operativas y financieras del negocio:
# valor total del inventario, conteo global de órdenes y lista de
# productos con stock crítico. La matriz de permisos (sección 2.6)
# prohíbe al Empleado ver estos datos — son cifras del negocio,
# no de sus propios pedidos.
# Ver: docs/roles/matriz-permisos.md sección 2.6.
#
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_supervisor
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
    # require_supervisor: Empleado no puede ver métricas del negocio.
    # Ver matriz-permisos.md sección 2.6 — todos los dashboards: ❌ Empleado.
    current_user: User = Depends(require_supervisor),
) -> DashboardSummary:
    """
    Devuelve las métricas de negocio en tiempo real.

    GET /api/v1/dashboard/summary
    Requiere: Supervisor, Administrador o Superadmin (Empleado → 403)

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

    ¿Por qué `current_user` está en la firma aunque no lo usemos?
    Porque `Depends(require_supervisor)` tiene un efecto secundario:
    verifica que el token JWT sea válido Y que el rol esté permitido.
    Sin esta línea, el endpoint sería público.
    """
    return await dashboard_service.get_dashboard_summary(db)
