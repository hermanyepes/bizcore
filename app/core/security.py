# ============================================================
# BizCore — Seguridad: hashing de contraseñas y tokens JWT
# ============================================================
#
# ESTE ARCHIVO TIENE DOS RESPONSABILIDADES:
#
# 1. CONTRASEÑAS (bcrypt)
#    ¿Por qué no guardamos la contraseña directamente?
#    Porque si alguien roba la BD, obtiene todas las contraseñas
#    en texto plano y puede usarlas en otros servicios (Gmail, banco).
#    Con bcrypt, solo guardamos una huella irreversible. Aunque
#    roben la BD, no pueden recuperar la contraseña original.
#
#    ¿Qué es bcrypt?
#    Un algoritmo de hash LENTO por diseño. MD5 y SHA256 son rápidos
#    — un atacante puede probar mil millones de combinaciones por
#    segundo. bcrypt puede configurarse para que cada intento tarde
#    100ms. Eso hace que un ataque de fuerza bruta sea imprácticamente
#    lento (años en vez de horas).
#
#    ¿Qué es el "salt"?
#    Un valor aleatorio que bcrypt agrega automáticamente antes de
#    hashear. Resultado: dos usuarios con la misma contraseña tienen
#    hashes completamente diferentes. Esto previene "rainbow tables"
#    (tablas precalculadas de hash → contraseña).
#
# 2. TOKENS JWT (JSON Web Token)
#    ¿Qué es un JWT?
#    Una cadena de texto codificada en Base64 con tres partes:
#    - Header: algoritmo usado ("HS256")
#    - Payload: datos del usuario (sub, rol, exp) — VISIBLE, no cifrado
#    - Signature: firma HMAC del header+payload con SECRET_KEY
#
#    La firma es lo que hace al JWT seguro. Si alguien modifica el
#    payload (ej: cambia "rol":"Empleado" → "rol":"Administrador"),
#    la firma ya no coincide y el servidor rechaza el token.
#
#    ¿Qué pasa si el token expira?
#    "exp" es una timestamp en el payload. El servidor verifica que
#    datetime.utcnow() < exp. Si expiró, devuelve 401 Unauthorized.
#
# ============================================================

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import jwt

from app.core.config import settings

# ============================================================
# Contraseñas con bcrypt directo (sin passlib)
# ============================================================
# passlib es una capa de abstracción sobre bcrypt que lleva años
# sin mantenimiento. bcrypt >= 4.0 cambió su API interna y passlib
# no se actualizó. Usamos bcrypt directamente: menos capas,
# menos superficie de error.
#
# bcrypt trabaja con bytes, no strings. Por eso:
# - encode(): convierte el string Python → bytes antes de hashear
# - decode(): convierte los bytes del hash → string para guardar en BD
# ============================================================


def hash_password(password: str) -> str:
    """
    Convierte una contraseña en texto plano en un hash bcrypt.

    El hash incluye el salt automáticamente — no necesitas manejarlo.
    Cada llamada produce un hash diferente aunque la contraseña sea igual.

    Ejemplo:
        hash_password("Accenture2024")
        → "$2b$12$K8HqO3vR1mN9..." (diferente cada vez)
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña en texto plano coincide con un hash bcrypt.

    ¿Cómo funciona sin "desencriptar"?
    bcrypt extrae el salt del hash guardado, hashea el plain_password
    con ese mismo salt, y compara el resultado. No necesita revertir el hash.

    Devuelve True si coinciden, False si no.

    Ejemplo:
        verify_password("Accenture2024", "$2b$12$K8HqO3...") → True
        verify_password("contraseña_mal", "$2b$12$K8HqO3...") → False
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ============================================================
# JWT — Creación y verificación de tokens
# ============================================================

def create_access_token(data: dict[str, Any]) -> str:
    """
    Crea un JWT firmado con los datos del usuario.

    ¿Qué va en `data`?
    Convencionalmente: {"sub": "id_del_usuario", "rol": "Administrador"}
    "sub" (subject) es el estándar JWT para identificar al usuario.

    El token expira en ACCESS_TOKEN_EXPIRE_MINUTES minutos (15 por defecto).
    Después de eso, el servidor lo rechaza aunque la firma sea válida.

    ¿Por qué 15 minutos?
    Si alguien roba el token (XSS, log expuesto), tiene acceso por máximo
    15 minutos. Un tiempo mayor aumenta la ventana de vulnerabilidad.

    Devuelve el JWT como string (lo que el cliente guarda y envía).
    """
    payload = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire  # jose/JWT entiende objetos datetime directamente

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Verifica y decodifica un JWT.

    ¿Qué verifica?
    1. Que la firma sea válida (no fue modificado)
    2. Que no haya expirado ("exp" en el payload)

    Si algo falla lanza JWTError — el endpoint que llama a esta
    función debe capturarla y devolver 401.

    Devuelve el payload como diccionario si todo está bien.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ============================================================
# Refresh tokens — generación y hashing
# ============================================================
#
# ¿POR QUÉ un token aleatorio en vez de un JWT para el refresh?
# Un JWT tiene payload visible (sub, exp, etc.) y puede usarse
# sin consultar la BD (es "stateless"). Eso es bueno para el
# access token, pero MALO para el refresh token: queremos poder
# revocarlo en cualquier momento (logout). Para revocar,
# necesitamos un registro en BD — así que el token pasa a ser
# "stateful" de todas formas. Un string aleatorio es más simple,
# más corto, y igual de seguro para este propósito.
#
# secrets.token_urlsafe(32):
# - Genera 32 bytes de entropía criptográfica (fuente: OS CSPRNG)
# - Los codifica en Base64url → resultado: 43 caracteres
# - "url-safe": solo usa A-Z, a-z, 0-9, -, _ (sin =, +, /)
# - 32 bytes = 256 bits de entropía → imposible de adivinar
# ============================================================


def create_refresh_token() -> str:
    """
    Genera un token aleatorio criptográficamente seguro.

    Devuelve un string de 43 caracteres Base64url.
    Este valor es el que el cliente guarda y envía en /refresh.

    Ejemplo: "kP3mN9vRqX2yTzW8jL5bC1dF6gH0sA7n-uE4oI"
    (diferente cada vez — 256 bits de entropía)
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """
    Calcula SHA256 del token para guardar en la BD.

    ¿Por qué no guardamos el token directamente?
    Si alguien roba la BD, obtiene los hashes — no los tokens reales.
    SHA256 es una función de un solo sentido: dado el hash,
    es computacionalmente imposible recuperar el token original.

    Devuelve 64 caracteres hexadecimales (SHA256 siempre es 256 bits = 64 hex).

    Ejemplo:
        hash_refresh_token("kP3mN9vR...") → "3a7f9b2c4d1e8f5a..."
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
