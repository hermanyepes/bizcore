# ============================================================
# BizCore — Tests de integración: endpoint /health
# ============================================================
#
# ¿Qué probamos aquí?
#   Que /health ejecuta un SELECT 1 real contra la BD y devuelve
#   el código HTTP correcto según el resultado:
#     - 200 con {status: "healthy", database: "ok"} si la BD responde
#     - 503 con {status: "unhealthy", database: "unreachable"} si falla
#
# ¿Por qué son tests de integración?
#   Porque necesitamos un cliente HTTP y una sesión de BD (aunque sea
#   SQLite en memoria) para verificar el flujo completo del endpoint.
#
# ============================================================

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db
from app.main import app


@pytest.mark.anyio
async def test_health_ok(client: AsyncClient):
    """
    Con BD funcional, /health devuelve 200 y {database: "ok"}.

    El fixture `client` ya inyecta SQLite en memoria como BD de prueba.
    SELECT 1 pasa en SQLite igual que en PostgreSQL.
    """
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "ok"}


@pytest.mark.anyio
async def test_health_db_unreachable():
    """
    Cuando db.execute() lanza una excepción, /health devuelve 503.

    Inyectamos una sesión mock que falla en execute() para simular
    que la BD no está disponible, sin necesidad de parar PostgreSQL.
    """

    async def failing_db():
        # Sesión mock que lanza al intentar cualquier query
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("connection refused")
        yield mock_session

    app.dependency_overrides[get_db] = failing_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            response = await ac.get("/health")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "unreachable"}
