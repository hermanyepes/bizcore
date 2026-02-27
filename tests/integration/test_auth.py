# ============================================================
# BizCore — Tests de integración: POST /api/v1/auth/login
# ============================================================
#
# "Integración" significa que probamos el flujo completo:
# cliente HTTP → endpoint → lógica → BD de prueba → respuesta.
#
# ANALOGÍA: no solo probamos si el chef sabe hacer la salsa.
# Probamos si el mesero toma el pedido correctamente, lo lleva
# a cocina, y trae el plato terminado al cliente.
#
# Los fixtures vienen de tests/conftest.py:
#   - client     → cliente HTTP con BD de prueba
#   - admin_user → usuario Administrador ya en la BD
#   - db         → sesión de BD (para crear usuarios especiales)
#
# ============================================================

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User

# ============================================================
# Happy path — credenciales correctas
# ============================================================


async def test_login_exitoso_devuelve_token(client: AsyncClient, admin_user: User):
    """
    POST /api/v1/auth/login con credenciales válidas debe:
    - Devolver 200 OK
    - Incluir un campo "access_token" en la respuesta
    - Incluir "token_type": "bearer"
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Admin1234"},
    )

    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # El token debe ser un string no vacío con 3 partes (header.payload.signature)
    token = data["access_token"]
    assert isinstance(token, str)
    assert len(token.split(".")) == 3


# ============================================================
# Errores esperados — el endpoint debe rechazar sin revelar info
# ============================================================


async def test_login_email_inexistente_devuelve_401(client: AsyncClient):
    """
    POST /login con un email que no existe en la BD debe devolver 401.

    IMPORTANTE: el mensaje debe ser genérico ("Credenciales inválidas"),
    no "email no encontrado". Esto previene que un atacante confirme
    qué emails existen en el sistema.
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
    POST /login con contraseña incorrecta debe devolver 401.

    El mismo error que "email no existe" — nunca revelamos cuál
    de los dos datos está mal.
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
    POST /login con un usuario inactivo (is_active=False) debe devolver 403.

    ¿Por qué 403 y no 401?
    401 = "No sé quién eres" (credenciales inválidas)
    403 = "Sé quién eres pero no puedes entrar" (cuenta desactivada)

    El usuario EXISTE y la contraseña ES correcta, pero está bloqueado.
    """
    # Crear un usuario inactivo directamente en la BD de prueba
    usuario_inactivo = User(
        document_id="9999999999",
        document_type="CC",
        full_name="Usuario Inactivo",
        email="inactivo@test.com",
        role="Empleado",
        password_hash=hash_password("Inactivo1234"),
        is_active=False,  # cuenta desactivada
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
    """
    POST /login sin body debe devolver 422 Unprocessable Entity.

    422 = el servidor entendió la petición pero los datos son inválidos.
    FastAPI valida el body automáticamente con Pydantic.
    """
    response = await client.post("/api/v1/auth/login")
    assert response.status_code == 422


async def test_login_email_formato_invalido_devuelve_422(client: AsyncClient):
    """
    POST /login con email malformado debe devolver 422.

    Pydantic valida que el email tenga formato válido antes de
    llegar a la lógica del endpoint.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "esto-no-es-un-email", "password": "Admin1234"},
    )
    assert response.status_code == 422
