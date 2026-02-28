# ============================================================
# BizCore — Router principal de la API v1
# ============================================================
#
# Este archivo es el punto de entrada de toda la API v1.
# Registra todos los routers de cada módulo bajo el prefijo
# /api/v1, y main.py solo necesita importar este único router.
#
# ¿Por qué versionar la API con /v1/?
# Si en el futuro cambias el contrato de la API (renombras campos,
# cambias comportamientos), puedes lanzar /v2 sin romper los
# clientes que todavía usan /v1. Es una práctica profesional estándar.
#
# Para agregar un nuevo módulo en el futuro:
#   from app.api.v1 import products
#   router.include_router(products.router)
#
# ============================================================

from fastapi import APIRouter

from app.api.v1 import auth, products, users

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(users.router)
router.include_router(products.router)
