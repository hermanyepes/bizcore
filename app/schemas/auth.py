# ============================================================
# BizCore — Schemas de autenticación
# ============================================================
#
# ANALOGÍA: estos schemas son los formularios del proceso de
# entrada al restaurante.
#
# LoginRequest   = el formulario que llenas en la puerta:
#                  "¿Cuál es tu correo y tu contraseña?"
#
# TokenResponse  = el carnet DOBLE que te dan cuando entras:
#                  - access_token: pase de 15 minutos (para entrar)
#                  - refresh_token: tarjeta de cliente frecuente
#                    (para pedir un nuevo pase sin volver a hacer fila)
#
# RefreshRequest = el formulario que llevas a la taquilla cuando
#                  tu pase de 15 minutos expiró:
#                  "Aquí está mi tarjeta de cliente. Dame uno nuevo."
#
# LogoutRequest  = el formulario para devolver la tarjeta de cliente:
#                  "No volveré hoy. Cancelen mi tarjeta."
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
    # llegar a la lógica de negocio.
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """
    Respuesta del servidor después de login o refresh exitosos.

    El cliente recibe AMBOS tokens:
    - access_token: JWT de corta duración (15 min). Se envía en cada
      petición autenticada como header "Authorization: Bearer <token>".
    - refresh_token: string aleatorio de larga duración (7 días).
      Angular lo guarda en memoria (o localStorage como segunda opción)
      y lo usa SOLO para llamar a POST /auth/refresh cuando el
      access_token expira.
    """

    access_token: str
    refresh_token: str
    # token_type siempre es "bearer" en OAuth2.
    # "Bearer" = "quien tenga este token puede usarlo".
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """
    Datos que el cliente envía para renovar el access token.

    POST /api/v1/auth/refresh
    Body: {"refresh_token": "kP3mN9vRqX2yTzW8..."}

    El servidor invalida el token recibido y emite uno nuevo
    (rotación). El cliente DEBE guardar el nuevo refresh_token
    que viene en la respuesta — el anterior ya no sirve.
    """

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """
    Datos que el cliente envía para cerrar sesión.

    POST /api/v1/auth/logout
    Body: {"refresh_token": "kP3mN9vRqX2yTzW8..."}

    El servidor revoca el refresh_token. A partir de ese momento
    no puede usarse para obtener nuevos access tokens.
    El access token vigente expirará solo en máximo 15 minutos.
    """

    refresh_token: str = Field(min_length=1)
