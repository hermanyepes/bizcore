# ============================================================
# BizCore — Tests de integración: middleware de security headers
# ============================================================
#
# ¿Qué probamos aquí?
#   Que el middleware `add_security_headers` en main.py inyecta
#   los 4 headers de seguridad en CADA respuesta HTTP de la app,
#   sin importar qué endpoint se llame.
#
# ¿Por qué son tests de integración y no unitarios?
#   Porque necesitamos hacer un request HTTP real (aunque sea en
#   memoria) para poder leer los headers de la respuesta.
#   No hay forma de probar un middleware sin pasar por la app.
#
# ANALOGÍA: es como verificar que el filtro de agua está instalado.
#   No pruebas el agua específica — pruebas que el filtro aparece
#   en cualquier agua que pase por la tubería.
#
# ============================================================

import pytest
from httpx import AsyncClient

# ============================================================
# Grupo 1 — Presencia y valor exacto de cada header
# ============================================================
# Cada test verifica un header individual contra el endpoint
# más simple de la app: GET / (el root que devuelve {app: ...}).
# Así aislamos el middleware de cualquier lógica de negocio.
# ============================================================

@pytest.mark.anyio
async def test_header_x_content_type_options(client: AsyncClient):
    """
    X-Content-Type-Options debe ser 'nosniff' en toda respuesta.

    Qué verifica: que el navegador no intente adivinar el tipo de
    archivo — solo confíe en el Content-Type que el servidor declara.
    """
    response = await client.get("/")
    assert response.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.anyio
async def test_header_x_frame_options(client: AsyncClient):
    """
    X-Frame-Options debe ser 'DENY' en toda respuesta.

    Qué verifica: que ninguna página del sitio pueda cargarse
    dentro de un <iframe> de otro dominio (protección anti-clickjacking).
    """
    response = await client.get("/")
    assert response.headers.get("x-frame-options") == "DENY"


@pytest.mark.anyio
async def test_header_strict_transport_security(client: AsyncClient):
    """
    Strict-Transport-Security debe forzar HTTPS por 1 año.

    Qué verifica: que el navegador recuerde usar HTTPS durante
    31536000 segundos (1 año) en este dominio y sus subdominios,
    aunque el usuario escriba http:// manualmente.
    """
    response = await client.get("/")
    hsts = response.headers.get("strict-transport-security")
    assert hsts == "max-age=31536000; includeSubDomains"


@pytest.mark.anyio
async def test_header_referrer_policy(client: AsyncClient):
    """
    Referrer-Policy debe ser 'strict-origin-when-cross-origin'.

    Qué verifica: que al navegar a otro dominio, el navegador
    solo envíe el origen (bizcore.com), nunca la URL completa
    con parámetros que podrían contener datos sensibles.
    """
    response = await client.get("/")
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


# ============================================================
# Grupo 2 — Los headers aparecen en cualquier endpoint
# ============================================================
# El middleware envuelve TODA la app. Si solo funcionara en `/`
# sería un bug crítico. Verificamos con /health que el middleware
# no está atado a una ruta específica.
# ============================================================

@pytest.mark.anyio
async def test_security_headers_presentes_en_health(client: AsyncClient):
    """
    Los 4 headers deben aparecer también en /health.

    Qué verifica: que el middleware aplica globalmente, no solo
    en el endpoint raíz. Si algún header falta aquí, significa
    que el middleware no está registrado a nivel de app.
    """
    response = await client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


# ============================================================
# Grupo 3 — Los headers aparecen en respuestas de error
# ============================================================
# Un middleware mal implementado podría saltarse respuestas de
# error (4xx/5xx). Verificamos que también aparecen en un 404.
# ============================================================

@pytest.mark.anyio
async def test_security_headers_presentes_en_404(client: AsyncClient):
    """
    Los headers de seguridad deben aparecer incluso en respuestas 404.

    Qué verifica: que el middleware no se salta respuestas de error.
    Un atacante que encuentra un endpoint inexistente también debe
    recibir los headers — no son solo para respuestas exitosas.
    """
    response = await client.get("/ruta-que-no-existe")
    # Confirmamos que es un 404 real
    assert response.status_code == 404
    # Y que los headers siguen presentes
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
