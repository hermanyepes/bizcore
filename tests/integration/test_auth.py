# ============================================================
# BizCore — Tests de integración: autenticación completa
# ============================================================
#
# Cubre los tres endpoints del módulo auth:
#   POST /api/v1/auth/login   — credenciales → tokens
#   POST /api/v1/auth/refresh — rotación de refresh token
#   POST /api/v1/auth/logout  — revocación de sesión
#
# Los fixtures vienen de tests/conftest.py:
#   - client              → cliente HTTP con BD de prueba
#   - admin_user          → usuario Administrador ya en la BD
#   - admin_refresh_token → refresh token válido del admin
#   - db                  → sesión de BD (para crear datos especiales)
#
# ============================================================

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, hash_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.user import User

# ============================================================
# POST /auth/login — Happy path y errores esperados
# ============================================================


async def test_login_exitoso_devuelve_access_y_refresh_token(
    client: AsyncClient, admin_user: User
):
    """
    POST /login con credenciales válidas debe:
    - Devolver 200 OK
    - Incluir "access_token" (JWT con 3 partes)
    - Incluir "refresh_token" (string opaco)
    - Incluir "token_type": "bearer"
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Admin1234"},
    )

    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # El access token es un JWT — tiene 3 partes separadas por punto
    access = data["access_token"]
    assert isinstance(access, str)
    assert len(access.split(".")) == 3

    # El refresh token es un string opaco (no JWT) — no tiene puntos
    refresh = data["refresh_token"]
    assert isinstance(refresh, str)
    assert len(refresh) > 20  # mínimo 20 chars (token_urlsafe(32) = 43 chars)


async def test_login_email_inexistente_devuelve_401(client: AsyncClient):
    """
    Email que no existe → 401 con mensaje genérico.
    No revelar si el email existe o no.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "noexiste@test.com", "password": "Admin1234"},
    )

    assert response.status_code == 401
    assert "Credenciales" in response.json()["detail"]


async def test_login_contraseña_incorrecta_devuelve_401(
    client: AsyncClient, admin_user: User
):
    """
    Email correcto + contraseña incorrecta → 401 con mismo mensaje que
    "email no existe". Nunca revelamos cuál de los dos datos está mal.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "ContraseñaMal"},
    )

    assert response.status_code == 401
    assert "Credenciales" in response.json()["detail"]


async def test_login_usuario_inactivo_devuelve_403(
    client: AsyncClient, db: AsyncSession
):
    """
    Usuario inactivo (is_active=False) → 403 Forbidden.

    403 y no 401 porque el servidor SÍ sabe quién es el usuario
    (credenciales válidas), pero la cuenta está desactivada.
    """
    usuario_inactivo = User(
        document_id="9999999999",
        document_type="CC",
        full_name="Usuario Inactivo",
        email="inactivo@test.com",
        role="Empleado",
        password_hash=hash_password("Inactivo1234"),
        is_active=False,
        join_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(usuario_inactivo)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactivo@test.com", "password": "Inactivo1234"},
    )

    assert response.status_code == 403
    assert "inactivo" in response.json()["detail"].lower()


async def test_login_sin_body_devuelve_422(client: AsyncClient):
    """Sin body → 422 Unprocessable Entity (validación Pydantic)."""
    response = await client.post("/api/v1/auth/login")
    assert response.status_code == 422


async def test_login_email_formato_invalido_devuelve_422(client: AsyncClient):
    """Email malformado → 422. Pydantic valida el formato antes del endpoint."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "esto-no-es-un-email", "password": "Admin1234"},
    )
    assert response.status_code == 422


async def test_login_rate_limit_bloquea_al_sexto_intento(
    client: AsyncClient, admin_user: User
):
    """
    /login tiene límite de 5 req/min por IP.
    El 6to intento → 429 Too Many Requests.
    El fixture `reset_rate_limiter` (autouse) garantiza contador en cero.
    """
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": "Admin1234"},
        )
        assert response.status_code == 200

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Admin1234"},
    )
    assert response.status_code == 429


# ============================================================
# POST /auth/refresh — Rotación de tokens
# ============================================================


async def test_refresh_exitoso_devuelve_nuevos_tokens(
    client: AsyncClient, admin_refresh_token: str
):
    """
    /refresh con un refresh token válido debe:
    - Devolver 200 OK
    - Incluir nuevos access_token y refresh_token
    - El nuevo refresh_token es diferente al original (rotación)
    """
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_refresh_token},
    )

    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # El nuevo refresh_token debe ser DIFERENTE al original — rotación
    assert data["refresh_token"] != admin_refresh_token

    # El nuevo access_token debe ser un JWT válido (3 partes)
    assert len(data["access_token"].split(".")) == 3


async def test_refresh_rota_el_token_anterior(
    client: AsyncClient, admin_refresh_token: str
):
    """
    Después de un /refresh exitoso, el token original es inválido.

    ROTACIÓN: cada /refresh invalida el token recibido y emite uno nuevo.
    Si un atacante roba el token original y lo intenta usar DESPUÉS
    de que el usuario ya hizo refresh, recibirá 401.
    """
    # Primer refresh — usa el token original
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_refresh_token},
    )
    assert response.status_code == 200

    # Intentar usar el token original de nuevo — debe fallar
    response2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_refresh_token},
    )
    assert response2.status_code == 401


async def test_refresh_con_nuevo_token_funciona(
    client: AsyncClient, admin_refresh_token: str
):
    """
    El nuevo refresh_token emitido por /refresh puede usarse para
    obtener otra renovación. La cadena de rotación funciona correctamente.
    """
    # Primera rotación
    response1 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_refresh_token},
    )
    assert response1.status_code == 200
    new_refresh = response1.json()["refresh_token"]

    # Segunda rotación con el token nuevo
    response2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert response2.status_code == 200


async def test_refresh_token_invalido_devuelve_401(client: AsyncClient):
    """
    /refresh con un token que no existe en la BD → 401.
    Un atacante que intente adivinar tokens recibe solo 401.
    """
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "esto-no-es-un-token-valido"},
    )
    assert response.status_code == 401


async def test_refresh_token_expirado_devuelve_401(
    client: AsyncClient, admin_user: User, db: AsyncSession
):
    """
    /refresh con un token cuya expires_at ya pasó → 401.

    Insertamos directamente en BD un token con expires_at en el pasado
    (sin pasar por /login) para simular el vencimiento.
    """
    # Crear un refresh token expirado directamente en la BD
    raw_token = "token-expirado-para-test-abc123"
    expired_token = RefreshToken(
        user_id=admin_user.document_id,
        token_hash=hash_refresh_token(raw_token),
        # expires_at en el pasado — este token ya venció
        expires_at=datetime.now(UTC) - timedelta(days=1),
        is_revoked=False,
        created_at=datetime.now(UTC),
    )
    db.add(expired_token)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw_token},
    )
    assert response.status_code == 401


async def test_refresh_usuario_inactivo_devuelve_403(
    client: AsyncClient, admin_user: User, db: AsyncSession, admin_refresh_token: str
):
    """
    Si el usuario fue desactivado DESPUÉS de obtener el refresh token,
    el /refresh debe devolver 403.

    Escenario real: admin desactiva un usuario mientras tiene sesión activa.
    El usuario tiene un refresh_token válido pero ya no puede renovarlo.
    """
    # Desactivar el usuario directamente en BD (simular acción del admin)
    admin_user.is_active = False
    await db.commit()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_refresh_token},
    )
    assert response.status_code == 403
    assert "inactivo" in response.json()["detail"].lower()


async def test_refresh_sin_body_devuelve_422(client: AsyncClient):
    """Sin body → 422. Pydantic valida que refresh_token es requerido."""
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 422


# ============================================================
# POST /auth/logout — Revocación de sesión
# ============================================================


async def test_logout_exitoso_devuelve_200(
    client: AsyncClient, admin_refresh_token: str
):
    """
    /logout con un refresh token válido debe:
    - Devolver 200 OK
    - Incluir un mensaje de confirmación
    """
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": admin_refresh_token},
    )

    assert response.status_code == 200
    assert "message" in response.json()


async def test_logout_luego_refresh_falla(
    client: AsyncClient, admin_refresh_token: str
):
    """
    Después de /logout, intentar /refresh con el mismo token → 401.

    Este es el flujo completo de logout:
    1. Cliente llama /logout con su refresh_token
    2. Servidor revoca el token
    3. Cliente ya no puede obtener nuevos access tokens
    4. La sesión efectivamente terminó
    """
    # Cerrar sesión
    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": admin_refresh_token},
    )
    assert logout_response.status_code == 200

    # Intentar renovar el access token con el refresh_token revocado
    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": admin_refresh_token},
    )
    assert refresh_response.status_code == 401


async def test_logout_token_invalido_devuelve_401(client: AsyncClient):
    """
    /logout con un token que no existe en la BD → 401.
    No se puede cerrar una sesión que no existe.
    """
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "token-que-no-existe"},
    )
    assert response.status_code == 401


async def test_logout_doble_devuelve_401(
    client: AsyncClient, admin_refresh_token: str
):
    """
    Hacer /logout dos veces con el mismo token → segundo intento da 401.

    Si alguien intercepta la solicitud de logout e intenta reproducirla,
    el segundo intento falla porque el token ya fue revocado.
    """
    # Primer logout — exitoso
    response1 = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": admin_refresh_token},
    )
    assert response1.status_code == 200

    # Segundo logout con el mismo token — debe fallar
    response2 = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": admin_refresh_token},
    )
    assert response2.status_code == 401


async def test_logout_sin_body_devuelve_422(client: AsyncClient):
    """Sin body → 422. Pydantic valida que refresh_token es requerido."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 422
