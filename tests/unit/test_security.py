# ============================================================
# BizCore — Tests unitarios: core/security.py
# ============================================================
#
# "Unitario" significa que probamos UNA función a la vez,
# sin BD, sin HTTP, sin dependencias externas.
#
# ANALOGÍA: probar si el chef sabe hacer la salsa, sin necesidad
# de que el restaurante esté abierto. La salsa funciona sola.
#
# ¿Qué probamos aquí?
#   - hash_password()      → produce un hash bcrypt válido
#   - verify_password()    → compara contraseñas correctamente
#   - create_access_token() → genera un JWT con los datos dados
#   - decode_access_token() → recupera el payload correctamente
#   - Errores de JWT       → tokens inválidos o manipulados
#
# ============================================================

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ============================================================
# Tests de contraseñas (bcrypt)
# ============================================================


def test_hash_password_produce_hash_bcrypt():
    """hash_password() debe producir un hash que empiece con $2b$ (identificador bcrypt)."""
    hashed = hash_password("MiContraseña123")
    # Todos los hashes bcrypt empiezan con $2b$ (o $2a$).
    # Esto confirma que estamos usando bcrypt y no MD5/SHA.
    assert hashed.startswith("$2b$")


def test_hash_password_resultado_diferente_cada_llamada():
    """
    Dos llamadas con la misma contraseña deben producir hashes distintos.

    ¿Por qué? Porque bcrypt agrega un "salt" aleatorio antes de hashear.
    Esto previene que dos usuarios con la misma contraseña tengan el
    mismo hash (lo que facilitaría ataques de tablas arcoíris).
    """
    hashed_1 = hash_password("misma_contraseña")
    hashed_2 = hash_password("misma_contraseña")
    assert hashed_1 != hashed_2  # salts diferentes → hashes diferentes


def test_verify_password_contraseña_correcta():
    """verify_password() debe devolver True cuando la contraseña coincide."""
    hashed = hash_password("ContraseñaCorrecta")
    result = verify_password("ContraseñaCorrecta", hashed)
    assert result is True


def test_verify_password_contraseña_incorrecta():
    """verify_password() debe devolver False cuando la contraseña NO coincide."""
    hashed = hash_password("ContraseñaCorrecta")
    result = verify_password("ContraseñaMal", hashed)
    assert result is False


def test_verify_password_string_vacio():
    """verify_password() debe devolver False con string vacío como contraseña."""
    hashed = hash_password("ContraseñaCorrecta")
    result = verify_password("", hashed)
    assert result is False


# ============================================================
# Tests de JWT (tokens de acceso)
# ============================================================


def test_create_access_token_devuelve_string():
    """create_access_token() debe devolver un string (el JWT)."""
    token = create_access_token({"sub": "1000000001", "role": "Administrador"})
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_tiene_tres_partes():
    """
    Un JWT válido siempre tiene exactamente 3 partes separadas por puntos:
    header.payload.signature
    """
    token = create_access_token({"sub": "1000000001", "role": "Administrador"})
    partes = token.split(".")
    assert len(partes) == 3


def test_decode_access_token_recupera_datos_originales():
    """
    decode_access_token() debe devolver los mismos datos que se usaron
    para crear el token (excepto 'exp' que se agrega automáticamente).
    """
    datos_originales = {"sub": "1000000001", "role": "Administrador"}
    token = create_access_token(datos_originales)
    payload = decode_access_token(token)

    assert payload["sub"] == "1000000001"
    assert payload["role"] == "Administrador"
    assert "exp" in payload  # se agrega automáticamente en create_access_token


def test_decode_access_token_con_token_invalido_lanza_jwerror():
    """
    decode_access_token() debe lanzar JWTError si el token es una basura.

    Esto simula lo que pasa si alguien envía un token falso o corrupto.
    El sistema debe rechazarlo, no crashear.
    """
    with pytest.raises(JWTError):
        decode_access_token("esto.no.es.un.jwt")


def test_decode_access_token_con_token_manipulado_lanza_jwerror():
    """
    Si alguien modifica el payload del JWT (ej: para cambiar su rol),
    la firma ya no coincide y debe lanzar JWTError.

    ANALOGÍA: es como falsificar una firma en un contrato.
    El banco verifica la firma original — si no coincide, rechaza.
    """
    import base64
    import json

    # Crear token legítimo
    token = create_access_token({"sub": "1000000001", "role": "Empleado"})
    header, payload_b64, signature = token.split(".")

    # Manipular el payload para intentar escalar privilegios
    payload_falso = {"sub": "1000000001", "role": "Administrador"}
    payload_b64_falso = (
        base64.urlsafe_b64encode(json.dumps(payload_falso).encode())
        .rstrip(b"=")
        .decode()
    )

    # Armar el token con el payload falso pero la firma original
    token_manipulado = f"{header}.{payload_b64_falso}.{signature}"

    with pytest.raises(JWTError):
        decode_access_token(token_manipulado)
