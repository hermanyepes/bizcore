# ============================================================
# BizCore — Configuración centralizada con pydantic-settings
# ============================================================
#
# ¿QUÉ HACE ESTE ARCHIVO?
# Lee las variables del archivo .env, las valida, y las expone
# como un objeto Python tipado. El resto de la app importa
# `settings` desde aquí — nadie llama `os.environ` directamente.
#
# ¿POR QUÉ pydantic-settings y no os.environ?
# os.environ siempre devuelve strings. Tendrías que convertir
# manualmente: int(os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"])
# pydantic-settings hace esa conversión automáticamente Y valida
# que el tipo sea correcto. Si pones "abc" donde espera un int,
# la app falla con un mensaje claro al arrancar.
#
# ¿QUÉ PASA SI FALTA UNA VARIABLE REQUERIDA?
# La app lanza ValidationError inmediatamente al importar este
# módulo. Eso es lo que queremos: fallo rápido y visible, no
# un error misterioso 10 minutos después cuando intenta conectar.
#
# ============================================================

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Todas las variables de configuración de la aplicación.

    pydantic-settings lee estas variables en este orden de prioridad:
    1. Variables de entorno del sistema operativo (más alta)
    2. Archivo .env
    3. Valores por defecto definidos aquí (más baja)

    Las que NO tienen valor por defecto son OBLIGATORIAS.
    Si no están en .env ni en el entorno, la app no arranca.
    """

    # --- Base de datos ---
    # Obligatoria: sin BD no hay aplicación
    # Formato: postgresql+asyncpg://usuario:contraseña@host:puerto/nombre_bd
    DATABASE_URL: str

    @field_validator("DATABASE_URL")
    @classmethod
    def reject_placeholder_url(cls, v: str) -> str:
        # Falla rápido si alguien arranca con el .env.example sin editar
        if "CAMBIA_" in v:
            raise ValueError(
                "DATABASE_URL contiene el placeholder 'CAMBIA_'. "
                "Edita .env con tus credenciales reales antes de arrancar."
            )
        return v

    # --- Seguridad JWT ---
    # Obligatoria: sin clave secreta no podemos firmar tokens
    SECRET_KEY: str
    # Opcional con valor por defecto: HS256 es el algoritmo estándar
    ALGORITHM: str = "HS256"
    # Opcional: 15 minutos es el estándar de seguridad
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    # Opcional: 7 días es el estándar de industria para refresh tokens.
    # Balance entre seguridad (si lo roban, tiene ventana limitada) y
    # comodidad (el usuario no tiene que volver a hacer login cada semana).
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Entropía del refresh token en bytes. 32 bytes = 256 bits de entropía.
    # NIST SP 800-63B exige mínimo 128 bits; usamos 256 para tener margen
    # ante futuros avances en criptoanálisis.
    REFRESH_TOKEN_ENTROPY_BYTES: int = 32

    # --- Rate limiting ---
    # 5 intentos de login por minuto por IP.
    # Derivado de OWASP: suficiente para un humano legítimo,
    # demasiado lento para un ataque de diccionario automatizado.
    LOGIN_RATE_LIMIT: str = "5/minute"
    # Operaciones autenticadas (refresh, logout): umbral más alto porque
    # el usuario ya demostró que tiene credenciales válidas.
    AUTHENTICATED_RATE_LIMIT: str = "20/minute"

    # --- CORS ---
    # Lista de orígenes permitidos. pydantic-settings acepta dos formatos desde .env:
    #   Formato JSON:  ALLOWED_ORIGINS=["http://localhost:4200","http://localhost:3000"]
    #   Formato CSV:   ALLOWED_ORIGINS=http://localhost:4200,http://localhost:3000
    # Default vacío: si falta en .env, CORS rechaza todo (fallo rápido y visible,
    # no un "funciona en dev pero silenciosamente roto en prod").
    ALLOWED_ORIGINS: list[str] = []

    # --- Entorno de ejecución ---
    # OBLIGATORIO: no tiene valor por defecto para forzar decisión explícita.
    # Valores válidos: "development" | "production"
    # En producción, deshabilita /docs y /redoc para evitar reconocimiento.
    # Añadir al .env: ENVIRONMENT=development
    ENVIRONMENT: str

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("development", "production"):
            raise ValueError(
                f"ENVIRONMENT debe ser 'development' o 'production', recibido: '{v}'. "
                "Revisa tu archivo .env."
            )
        return v

    # --- Configuración del archivo .env ---
    # model_config le dice a pydantic-settings CÓMO leer la configuración.
    # env_file: busca este archivo en el directorio de trabajo
    # env_file_encoding: el archivo .env está en UTF-8
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# ============================================================
# Instancia única de Settings (patrón Singleton)
# ============================================================
#
# ¿POR QUÉ @lru_cache?
# Sin lru_cache, cada vez que alguien importa `get_settings()`
# y la llama, pydantic-settings abriría y leería el archivo .env
# de nuevo. Con lru_cache, la primera llamada lee el archivo,
# guarda el resultado en memoria, y todas las llamadas siguientes
# devuelven el mismo objeto sin tocar el disco.
#
# ¿POR QUÉ una función y no simplemente `settings = Settings()`?
# Para testing: en los tests podemos reemplazar `get_settings`
# con una función que devuelve una config de prueba diferente,
# sin necesidad de un archivo .env real en el entorno de CI.
#
# ============================================================
@lru_cache
def get_settings() -> Settings:
    return Settings()


# Instancia lista para importar directamente
# Uso: from app.core.config import settings
settings = get_settings()
