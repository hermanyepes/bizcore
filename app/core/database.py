# ============================================================
# BizCore — Configuración de la base de datos con SQLAlchemy async
# ============================================================
#
# CONCEPTOS CLAVE:
#
# 1. ¿Qué es un "engine"?
#    El motor de conexión. Mantiene un pool de conexiones abiertas
#    a PostgreSQL listas para usar. No ejecuta queries — solo
#    administra las conexiones. Piénsalo como el "pool de empleados"
#    esperando trabajo.
#
# 2. ¿Qué es una "session"?
#    Una unidad de trabajo. Cuando necesitas hacer queries, abres
#    una sesión, haces tus operaciones, y la cierras. La sesión
#    rastrean todos los cambios y los envía a la BD en un solo
#    momento (cuando haces commit). Piénsalo como una "conversación"
#    con la BD con inicio y fin definidos.
#
# 3. ¿Por qué async?
#    PostgreSQL tarda tiempo en responder (aunque sea milisegundos).
#    Con código synchronous, FastAPI bloquea el servidor esperando.
#    Con async, FastAPI puede atender otras solicitudes mientras
#    espera la respuesta de la BD. Resultado: más usuarios atendidos
#    con el mismo servidor.
#
# 4. ¿Qué es DeclarativeBase?
#    La clase base de SQLAlchemy de la que heredan todos los modelos.
#    Cuando defines `class Usuario(Base)`, SQLAlchemy sabe que esa
#    clase representa una tabla en la BD.
#
# ============================================================

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ============================================================
# Motor de conexión (Engine)
# ============================================================
# create_async_engine crea el pool de conexiones.
#
# echo=False en producción: si fuera True, SQLAlchemy imprimiría
# cada query SQL en la consola — útil para debug, no para producción.
#
# pool_pre_ping=True: antes de usar una conexión del pool, verifica
# que siga activa. Previene errores si PostgreSQL reinició o
# la conexión se cayó por timeout de red.
# ============================================================
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


# ============================================================
# Fábrica de sesiones (Session Factory)
# ============================================================
# async_sessionmaker crea una "plantilla" para crear sesiones.
# Cada vez que llamamos AsyncSessionLocal() obtenemos una sesión
# nueva con estas configuraciones:
#
# class_=AsyncSession: sesiones async (no bloquean el servidor)
# expire_on_commit=False: después de un commit, los objetos Python
#   siguen siendo accesibles sin necesidad de hacer otro query.
#   Sin esto, al acceder a `usuario.nombre` después de un commit
#   SQLAlchemy haría un query extra automáticamente.
# ============================================================
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ============================================================
# Clase Base para los modelos SQLAlchemy
# ============================================================
# Todos los modelos (Usuario, Producto, Pedido...) heredan de Base.
# Esto le dice a SQLAlchemy que son tablas de la BD.
#
# ¿Por qué definir Base aquí y no en cada modelo?
# Porque Alembic necesita saber cuáles son TODOS los modelos para
# generar migraciones. Al importar Base desde un solo lugar e
# importar todos los modelos que heredan de ella, Alembic puede
# descubrirlos automáticamente.
# ============================================================
class Base(DeclarativeBase):
    pass
