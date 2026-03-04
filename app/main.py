# ============================================================
# BizCore — Punto de entrada de la aplicación FastAPI
# ============================================================
#
# CONCEPTOS CLAVE DE ESTE ARCHIVO:
#
# 1. ¿Qué es FastAPI?
#    Un framework web. Su trabajo es: recibir una petición HTTP,
#    pasarla a la función correcta (según la URL y el método),
#    y devolver la respuesta como JSON.
#
# 2. ¿Qué es una instancia de FastAPI?
#    El objeto `app` es la aplicación completa. Todo parte de aquí:
#    los routers, el middleware de CORS, los eventos de inicio/cierre.
#
# 3. ¿Qué es CORS?
#    Cross-Origin Resource Sharing. Por defecto, un navegador BLOQUEA
#    solicitudes de un origen diferente al del servidor. Angular corre
#    en localhost:4200 y FastAPI en localhost:8000 — son orígenes
#    distintos. CORS le dice a FastAPI qué orígenes puede aceptar.
#
# 4. ¿Qué es un "lifespan"?
#    Un context manager que define qué pasa cuando la app ARRANCA
#    (startup) y cuando SE CIERRA (shutdown). Aquí inicializamos
#    la conexión a la BD al arrancar y la cerramos al salir.
#
# ============================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_router
from app.core.config import settings
from app.core.database import engine
from app.core.limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejador del ciclo de vida de la aplicación.

    Todo el código ANTES de `yield` corre al INICIAR la app.
    Todo el código DESPUÉS de `yield` corre al CERRAR la app.
    """
    # === STARTUP ===
    print("BizCore arrancando...")
    print("BD conectada:", settings.DATABASE_URL.split("@")[-1])  # no exponer credenciales en el log
    print("Aplicación lista en http://localhost:8000/docs")

    yield  # aquí corre la app normalmente

    # === SHUTDOWN ===
    # Cierra todas las conexiones del pool al apagar el servidor.
    # Sin esto, PostgreSQL podría quedar con conexiones abiertas huérfanas.
    await engine.dispose()
    print("BizCore cerrado. Conexiones liberadas.")


# ============================================================
# Creación de la instancia FastAPI
# ============================================================
app = FastAPI(
    title="BizCore API",
    description=(
        "Sistema de gestión empresarial. "
        "CRUD de usuarios, productos, inventario, pedidos y proveedores."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Registrar el limiter en el estado de la app.
# slowapi lo lee desde `app.state.limiter` cuando procesa
# el decorador @limiter.limit() en cada endpoint.
app.state.limiter = limiter

# Manejador de error 429 Too Many Requests.
# Cuando el limiter rechaza una solicitud, lanza RateLimitExceeded.
# Este handler la convierte en un 429 con un mensaje claro al cliente.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================================================
# Middleware de CORS
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ============================================================
# Registro de routers
# ============================================================
# Un solo include_router aquí. api_router internamente
# ya contiene todos los routers (auth, users, etc.)
app.include_router(api_router)


# ============================================================
# Endpoints de verificación
# ============================================================

@app.get("/")
async def root():
    """Confirmación de que el servidor está corriendo."""
    return {
        "app": "BizCore API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Los sistemas de monitoreo llaman esto periódicamente.
    Si responde 200, el servicio está sano.
    """
    return {
        "status": "healthy",
        "database": settings.DATABASE_URL.split("@")[-1],  # muestra host/db sin credenciales
    }
