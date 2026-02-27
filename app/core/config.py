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

    # --- Seguridad JWT ---
    # Obligatoria: sin clave secreta no podemos firmar tokens
    SECRET_KEY: str
    # Opcional con valor por defecto: HS256 es el algoritmo estándar
    ALGORITHM: str = "HS256"
    # Opcional: 15 minutos es el estándar de seguridad
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # --- CORS ---
    # Lista de orígenes permitidos. pydantic-settings convierte
    # automáticamente "http://localhost:4200,http://localhost:3000"
    # (el string del .env) en ["http://localhost:4200", "http://localhost:3000"]
    ALLOWED_ORIGINS: list[str] = ["http://localhost:4200"]

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
