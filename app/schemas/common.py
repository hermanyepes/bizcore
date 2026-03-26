# ============================================================
# Schemas compartidos — reutilizables en todos los módulos
# ============================================================
# Este archivo agrupa schemas que NO pertenecen a un módulo
# específico (usuarios, productos, etc.) sino que sirven
# como moldes genéricos para cualquier recurso de la API.
#
# Contiene tres schemas:
#   1. PaginatedResponse[T] — respuesta paginada genérica (v1)
#   2. ErrorDetail          — detalle de error para el sobre (v2)
#   3. APIResponse[T]       — sobre estándar de respuesta    (v2)
# ============================================================

from typing import Self, TypeVar

from pydantic import BaseModel

# TypeVar define el "hueco en blanco" del molde genérico.
# La convención es usar T (de "Type"), pero podría llamarse
# ItemType, Elemento, etc. — es solo un nombre de marcador.
# bound=BaseModel garantiza que solo se puedan usar subclases
# de Pydantic como valor concreto de T.
T = TypeVar("T", bound=BaseModel)


# ============================================================
# 1. PaginatedResponse[T] — usado en v1
# ============================================================
class PaginatedResponse[T: BaseModel](BaseModel):
    """
    Schema genérico para respuestas paginadas.

    Uso:
        UserPaginated = PaginatedResponse[UserResponse]
        ProductPaginated = PaginatedResponse[ProductResponse]

    Al especializar T, Pydantic genera una clase concreta
    con validación estricta del tipo de los ítems.
    """

    # Lista de ítems de la página actual.
    # Su tipo exacto depende de T:
    #   PaginatedResponse[UserResponse]     → items: list[UserResponse]
    #   PaginatedResponse[ProductResponse]  → items: list[ProductResponse]
    items: list[T]

    # Cantidad total de registros en la base de datos
    # (no solo los de esta página)
    total: int

    # Número de la página que se está devolviendo (base 1)
    page: int

    # Cuántos registros se muestran por página
    page_size: int

    # Total de páginas = ceil(total / page_size)
    # Se incluye aquí para que el frontend no tenga que calcularlo
    pages: int


# ============================================================
# 2. ErrorDetail — el contenido de la caja cuando algo salió mal
# ============================================================
class ErrorDetail(BaseModel):
    """
    Describe un error de negocio de forma estructurada.

    ANALOGÍA: es la nota dentro de la caja del repartidor cuando
    el pedido falló. Siempre tiene el mismo formato: un código
    (para que el código lo procese) y un mensaje (para el usuario).

    Ejemplos de uso:
        ErrorDetail(code="not_found",      message="Usuario 1000000001 no existe.")
        ErrorDetail(code="already_exists", message="El email ya está registrado.")
        ErrorDetail(code="inactive",       message="El proveedor está desactivado.")
    """

    # Identificador de máquina — snake_case, sin espacios.
    # El frontend puede hacer switch(error.code) para manejar
    # cada caso de forma específica sin depender de strings de mensaje.
    code: str

    # Mensaje legible para el humano (o para mostrar en la UI).
    # Puede cambiar sin romper el frontend, porque el frontend
    # usa `code` para la lógica y `message` solo para mostrarlo.
    message: str


# ============================================================
# 3. APIResponse[T] — el sobre estándar (diseñado para v2)
# ============================================================
class APIResponse[T: BaseModel](BaseModel):
    """
    Sobre estándar para todas las respuestas de la API v2.

    ANALOGÍA: es la caja del repartidor con etiqueta estándar.
    - success=True  → el pedido llegó bien, `data` tiene el contenido
    - success=False → algo salió mal, `error` describe qué pasó
    `data` y `error` son mutuamente exclusivos: si uno tiene valor,
    el otro es None. Nunca ambos llenos, nunca ambos vacíos.

    Uso en un endpoint v2:
        return APIResponse.ok(UserResponse.model_validate(user))
        return APIResponse.fail("not_found", "Usuario no existe.")

    Respuesta JSON exitosa:
        { "success": true,  "data": { ... }, "error": null }

    Respuesta JSON de error:
        { "success": false, "data": null,    "error": { "code": "...", "message": "..." } }
    """

    # ¿Salió bien la operación?
    # True  → data tiene el resultado
    # False → error describe el problema
    success: bool

    # El payload de la respuesta. Su tipo depende de T:
    #   APIResponse[UserResponse]    → data: UserResponse | None
    #   APIResponse[list[UserResponse]] → data: list[UserResponse] | None
    # Es None cuando success=False.
    data: T | None = None

    # El detalle del error. Es None cuando success=True.
    error: ErrorDetail | None = None

    # ----------------------------------------------------------
    # Factory methods — constructores rápidos para los endpoints
    # ----------------------------------------------------------
    # ¿Por qué @classmethod y no funciones sueltas?
    # Porque Self hace referencia a la clase exacta que se esté
    # usando. Si en el futuro se hereda de APIResponse, Self
    # apuntará a la subclase, no a APIResponse. Es más robusto
    # que hardcodear el nombre de la clase.
    # ----------------------------------------------------------

    @classmethod
    def ok(cls, data: T) -> Self:
        """
        Construye una respuesta exitosa.

        Uso:
            return APIResponse.ok(UserResponse.model_validate(user))
        """
        # Caja ✅: success=True, data con el contenido, error vacío
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str) -> Self:
        """
        Construye una respuesta de error.

        Uso:
            return APIResponse.fail("not_found", "Usuario 1000000001 no existe.")
        """
        # Caja ❌: success=False, data vacío, error con el detalle
        return cls(
            success=False, data=None, error=ErrorDetail(code=code, message=message)
        )
