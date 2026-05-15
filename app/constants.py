# ============================================================
# BizCore — Constantes globales de la aplicación
# ============================================================

from enum import StrEnum


class UserRole(StrEnum):
    # Dueño del software o soporte técnico — privilegio máximo, solo asignable via seed.
    SUPERADMIN = "Superadmin"
    # Gerente o dueño de la pyme — gestiona usuarios (excepto Superadmins) y todos los módulos.
    ADMIN = "Administrador"
    # Jefe de operaciones — CRUD de productos, inventario, proveedores y órdenes. Sin acceso a usuarios.
    SUPERVISOR = "Supervisor"
    # Vendedor o cajero — solo sus propias órdenes y catálogo de productos (sin costos ni márgenes).
    EMPLOYEE = "Empleado"
