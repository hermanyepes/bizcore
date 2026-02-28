# ============================================================
# BizCore — Fixtures compartidas para todos los tests
# ============================================================
#
# conftest.py es un archivo especial de pytest.
# Las "fixtures" definidas aquí son funciones que preparan el
# entorno antes de un test (y lo limpian después).
#
# ANALOGÍA: conftest.py es el inspector de sanidad que monta
# una "cocina espejo" antes de cada prueba:
#   1. Instala una BD SQLite en memoria (la cocina de prueba)
#   2. Crea las tablas (los utensilios)
#   3. Inserta usuarios ficticios (los ingredientes de prueba)
#   4. Conecta el cliente HTTP a esa cocina (no a la real)
#   5. Al terminar cada test, bota todo y empieza fresco
#
# ¿Por qué SQLite en vez de PostgreSQL para tests?
#   - No necesita un servidor externo corriendo
#   - "en memoria" = cuando el test termina, la BD desaparece sola
#   - Es suficientemente compatible para probar nuestra lógica CRUD
#
# ¿Por qué "en memoria" (/:memory:)?
#   Porque cuando Python termina el test, la memoria se libera.
#   No quedan residuos: cada test empieza con una BD virgen.
#
# "sqlite+aiosqlite" = SQLite (motor de BD) + aiosqlite (driver async).
# Necesitamos el driver async porque nuestros endpoints son async.
#
# ============================================================

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.security import hash_password
from app.dependencies import get_db
from app.main import app
from app.models.product import Product
from app.models.user import User

# URL de la BD de prueba — SQLite en memoria, desaparece al terminar el test
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ============================================================
# Fixture: engine
# ============================================================
# scope="function" (por defecto) = se ejecuta una vez POR TEST.
# Cada test recibe una BD en memoria nueva y vacía.
# Aislamiento total: lo que hace un test no afecta a otro.
# ============================================================
@pytest.fixture
async def engine():
    """
    Motor de BD SQLite en memoria — uno nuevo por cada test.

    Crea todas las tablas al inicio y las destruye al final.
    El `yield` separa el "antes" (setup) del "después" (teardown).
    """
    # Crear el motor apuntando a la BD en memoria
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Crear las tablas (equivalente a ejecutar CREATE TABLE para cada modelo)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine  # aquí corre el test

    # Limpiar: destruir tablas y cerrar conexiones
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


# ============================================================
# Fixture: db
# ============================================================
# Una sesión de BD conectada al engine de prueba.
# La misma sesión se comparte entre el test directo y el cliente HTTP
# (ver fixture `client` abajo), garantizando que todos ven los
# mismos datos durante el test.
# ============================================================
@pytest.fixture
async def db(engine):
    """Sesión de BD de prueba lista para usar en los tests."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ============================================================
# Fixture: client
# ============================================================
# Cliente HTTP que apunta a nuestra app FastAPI.
#
# Truco clave: sobreescribimos la dependencia `get_db` de FastAPI
# para que los endpoints usen la BD de PRUEBA (SQLite en memoria)
# en vez de la real (PostgreSQL).
#
# Sin esto, los endpoints llamarían a PostgreSQL durante los tests.
# Con esto, todo queda aislado en la BD de prueba.
#
# ASGITransport: hace peticiones HTTP directamente a la app ASGI
# en memoria, sin abrir un puerto de red. Es más rápido y no
# requiere que uvicorn esté corriendo.
# ============================================================
@pytest.fixture
async def client(db: AsyncSession):
    """
    Cliente HTTP con la BD de prueba inyectada.

    Comparte la MISMA sesión `db` que los fixtures de datos
    (admin_user, employee_user), así los endpoints ven los
    usuarios que los fixtures insertaron.
    """
    # Reemplazar get_db: siempre devuelve la sesión de prueba
    async def override_get_db():
        yield db  # sin crear una nueva sesión — usamos la del fixture

    # Inyectar el reemplazo en la app
    app.dependency_overrides[get_db] = override_get_db

    # Crear el cliente HTTP que apunta a la app en memoria
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    # Restaurar get_db original al terminar el test
    app.dependency_overrides.clear()


# ============================================================
# Fixture: admin_user
# ============================================================
# Crea un usuario Administrador directamente en la BD de prueba.
# Lo insertamos directo (sin pasar por el endpoint POST /users)
# para no hacer que unos tests dependan de otros.
#
# ¿Por qué datetime.now(UTC) explícito?
# SQLite no tiene la función server_default=func.now() de PostgreSQL.
# Seteando el valor desde Python, evitamos problemas de compatibilidad.
# ============================================================
@pytest.fixture
async def admin_user(db: AsyncSession):
    """Usuario Administrador disponible en la BD de prueba."""
    user = User(
        document_id="1000000001",
        document_type="CC",
        full_name="Admin Test",
        email="admin@test.com",
        role="Administrador",
        password_hash=hash_password("Admin1234"),
        is_active=True,
        join_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def employee_user(db: AsyncSession):
    """
    Usuario Empleado disponible en la BD de prueba.

    Útil para probar que los endpoints restringidos a Administrador
    devuelven 403 cuando los intenta un Empleado.
    """
    user = User(
        document_id="2000000002",
        document_type="CC",
        full_name="Empleado Test",
        email="empleado@test.com",
        role="Empleado",
        password_hash=hash_password("Empleado1234"),
        is_active=True,
        join_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ============================================================
# Fixtures de tokens JWT
# ============================================================
# Llaman al endpoint de login real para obtener un token válido.
# Así probamos implícitamente que el login funciona como prerequisito.
# Si el login falla, el assert explota aquí y el mensaje de error
# es claro: "el problema es el login, no el endpoint que estás probando".
# ============================================================
@pytest.fixture
async def admin_token(client: AsyncClient, admin_user: User) -> str:
    """Token JWT válido de un Administrador."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Admin1234"},
    )
    assert response.status_code == 200, f"Login de admin falló: {response.json()}"
    return response.json()["access_token"]


@pytest.fixture
async def product(db: AsyncSession):
    """
    Producto de prueba disponible en la BD antes de cada test.

    Lo insertamos directo (sin pasar por POST /products) por la misma
    razón que admin_user: los tests de productos no deben depender
    de que el endpoint de creación funcione correctamente.

    ¿Por qué created_at explícito?
    SQLite no tiene server_default=func.now() de PostgreSQL.
    Seteando el valor desde Python evitamos el error "NOT NULL constraint".
    """
    p = Product(
        name="Café Especial",
        description="Café de origen colombiano",
        price=15000,
        stock=100,
        category="Bebidas",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest.fixture
async def employee_token(client: AsyncClient, employee_user: User) -> str:
    """Token JWT válido de un Empleado."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "empleado@test.com", "password": "Empleado1234"},
    )
    assert response.status_code == 200, f"Login de empleado falló: {response.json()}"
    return response.json()["access_token"]
