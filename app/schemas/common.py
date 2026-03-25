# ============================================================
# Schemas compartidos — reutilizables en todos los módulos
# ============================================================
# Este archivo agrupa schemas que NO pertenecen a un módulo
# específico (usuarios, productos, etc.) sino que sirven
# como moldes genéricos para cualquier recurso de la API.
# ============================================================

from typing import Generic, TypeVar

from pydantic import BaseModel

# TypeVar define el "hueco en blanco" del molde genérico.
# La convención es usar T (de "Type"), pero podría llamarse
# ItemType, Elemento, etc. — es solo un nombre de marcador.
# bound=BaseModel garantiza que solo se puedan usar subclases
# de Pydantic como valor concreto de T.
T = TypeVar("T", bound=BaseModel)


class PaginatedResponse(BaseModel, Generic[T]):
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
