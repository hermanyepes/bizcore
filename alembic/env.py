# ============================================================
# Alembic env.py — Configuración del entorno de migraciones
# ============================================================
#
# ¿QUÉ HACE ESTE ARCHIVO?
# Alembic lo ejecuta cada vez que corres `alembic upgrade head`
# o `alembic revision --autogenerate`. Define:
# 1. De dónde viene la URL de la BD (nuestro .env via settings)
# 2. Qué modelos debe conocer para detectar cambios (target_metadata)
# 3. Cómo conectarse (modo async, porque nuestro engine es async)
#
# ¿POR QUÉ importar los modelos aquí?
# SQLAlchemy registra cada modelo en Base.metadata cuando lo importas.
# Si no importas el modelo, Alembic no sabe que esa tabla existe y
# no la incluye en el --autogenerate. Resultado: migración vacía.
#
# ¿POR QUÉ run_sync dentro de async?
# Alembic es synchronous internamente — no tiene soporte async nativo.
# La solución oficial: crear un engine async, abrir una conexión async,
# y dentro de esa conexión llamar a Alembic en modo sync con run_sync().
#
# ============================================================

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# --- Configuración de Alembic ---
alembic_cfg = context.config

if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

# --- Importar Base y TODOS los modelos ---
# Base.metadata acumula la definición de todas las tablas de los
# modelos que hereden de Base. Si no importas un modelo aquí,
# Alembic no sabe que esa tabla existe.
import app.models.user  # noqa: E402, F401
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

# target_metadata: le dice a Alembic cuál es el "estado deseado"
# de la BD. Al compararlo con el estado real, genera los cambios.
target_metadata = Base.metadata


# ============================================================
# Modo OFFLINE — genera SQL sin conectarse a la BD
# Útil para revisar qué SQL va a ejecutar antes de aplicarlo.
# Uso: alembic upgrade head --sql
# ============================================================
def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# Modo ONLINE — se conecta a la BD y aplica los cambios
# Es el modo normal. Alembic se conecta, compara, y ejecuta.
# ============================================================
def do_run_migrations(connection):
    """
    Función sync que Alembic puede ejecutar dentro de run_sync().
    Recibe una conexión ya abierta y corre las migraciones.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # compare_type=True: detecta cambios de tipo de columna
        # (ej: VARCHAR(15) → VARCHAR(20)). Sin esto, Alembic ignora
        # cambios de tamaño en columnas existentes.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Crea un engine async, abre una conexión, y llama a Alembic
    en modo sync dentro de esa conexión.

    asyncpg (nuestro driver) es async puro — no puede usarse en
    modo sync directamente. Por eso necesitamos este puente:
    conn.run_sync(do_run_migrations) ejecuta la función sync
    de Alembic dentro del contexto async de la conexión.
    """
    engine = create_async_engine(settings.DATABASE_URL)

    async with engine.begin() as conn:
        await conn.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """Punto de entrada sync que lanza el proceso async."""
    asyncio.run(run_async_migrations())


# --- Punto de entrada principal ---
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
