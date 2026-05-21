# ============================================================
# BizCore — Tests de integración: rate limiting autenticado (HU-061)
# ============================================================
#
# ¿Qué probamos aquí?
#   Que los endpoints autenticados respetan sus límites de velocidad:
#   - GET list/detail: AUTHENTICATED_RATE_LIMIT = 20/minute por IP
#   - POST/PUT/DELETE:                             30/minute por IP
#
# ¿Cómo funciona el reset entre tests?
#   La fixture `reset_rate_limiter` (autouse en conftest.py) limpia
#   todos los contadores antes de cada test. Cada test empieza con
#   slate limpio — sin "contaminación" de tests anteriores.
#
# ¿Por qué estas cantidades?
#   GET: enviamos 25 requests con límite de 20 → los últimos 5 son 429.
#   POST: enviamos 31 requests con límite de 30 → el último es 429.
#
# ============================================================

import pytest
from httpx import AsyncClient

from app.models.user import User


# ============================================================
# GET /api/v1/users — límite 20/minute
# ============================================================


@pytest.mark.anyio
async def test_get_users_rate_limited(client: AsyncClient, admin_token: str):
    """
    25 GET seguidos a /api/v1/users deben producir 429 a partir del request 21.

    Qué verifica: que list_users aplica AUTHENTICATED_RATE_LIMIT (20/minute).
    Los primeros 20 deben ser 200. Del 21 en adelante, 429.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    statuses = []

    for _ in range(25):
        r = await client.get("/api/v1/users/", headers=headers)
        statuses.append(r.status_code)

    # Las primeras 20 respuestas deben ser 200
    assert all(s == 200 for s in statuses[:20]), (
        f"Se esperaban 200 en los primeros 20 requests, se obtuvo: {statuses[:20]}"
    )
    # Del request 21 en adelante, el limiter debe bloquear con 429
    assert all(s == 429 for s in statuses[20:]), (
        f"Se esperaban 429 en los requests 21-25, se obtuvo: {statuses[20:]}"
    )


# ============================================================
# POST /api/v1/users — límite 30/minute
# ============================================================


@pytest.mark.anyio
async def test_post_user_rate_limited(client: AsyncClient, admin_token: str):
    """
    31 POST seguidos a /api/v1/users deben producir 429 en el request 31.

    Qué verifica: que create_user aplica el límite de escritura (30/minute).
    Los primeros 30 pueden devolver 201 o 409 (si el usuario ya existe),
    pero todos deben ser respondidos por la app. El request 31 debe ser 429.

    Nota: el rate limiter actúa ANTES de la lógica de negocio, así que
    el 429 llega sin importar si el body es válido o si el usuario ya existe.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    statuses = []

    for i in range(31):
        r = await client.post(
            "/api/v1/users/",
            headers=headers,
            json={
                "document_id": f"8000{i:06d}",
                "document_type": "CC",
                "full_name": f"Rate Test {i}",
                "email": f"ratetest{i}@test.com",
                "role": "Empleado",
                "password": "TestPass@42",  # pragma: allowlist secret
                "join_date": "2024-01-01",
            },
        )
        statuses.append(r.status_code)

    # Los primeros 30 no deben ser 429 (pueden ser 201 o 409)
    assert all(s != 429 for s in statuses[:30]), (
        f"Requests 1-30 no deben ser 429, se obtuvo: {statuses[:30]}"
    )
    # El request 31 debe ser bloqueado
    assert statuses[30] == 429, (
        f"Se esperaba 429 en el request 31, se obtuvo: {statuses[30]}"
    )
