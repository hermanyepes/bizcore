# ============================================================
# BizCore — Schemas de autenticación
# ============================================================
#
# ANALOGÍA: estos schemas son los formularios del proceso de
# entrada al restaurante.
#
# LoginRequest  = el formulario que llenas en la puerta:
#                 "¿Cuál es tu correo y tu contraseña?"
#
# TokenResponse = el carnet que te dan cuando entras:
#                 "Aquí tienes tu pase. Muéstralo en cada mesa."
#
# ¿POR QUÉ Pydantic y no un diccionario normal?
# Un diccionario acepta cualquier cosa sin quejarse:
#   {"correo": 12345, "password": None}  ← FastAPI lo recibiría sin error
#
# Pydantic valida automáticamente:
#   - correo debe ser string con formato de email
#   - password debe ser string no vacío
# Si algo falla, FastAPI devuelve 422 Unprocessable Entity con el
# detalle exacto del error, sin que escribas una sola línea de
# validación manual.
#
# ============================================================

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """
    Datos que el cliente envía para hacer login.

    POST /api/v1/auth/login
    Body: {"email": "herman@gmail.com", "password": "MiContraseña123"}
    """

    email: EmailStr
    # Field(min_length=1): rechaza contraseñas vacías antes de
    # llegar a la lógica de negocio. Sin esto, alguien podría enviar
    # password="" y el error llegaría más tarde y sería más confuso.
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """
    Respuesta del servidor después de un login exitoso.

    El cliente recibe esto y guarda `access_token` en memoria
    (no en localStorage — explicado en GUIA_APRENDIZAJE.md).
    """

    access_token: str
    # token_type siempre es "bearer" en OAuth2.
    # "Bearer" significa "quien tenga este token puede usarlo".
    # Es el tipo estándar para JWT en APIs REST.
    token_type: str = "bearer"
