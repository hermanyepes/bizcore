# ============================================================
# BizCore — Tests unitarios: schemas/common.py
# ============================================================
#
# ANALOGÍA: probamos las tres cajas del almacén (ErrorDetail,
# APIResponse.ok, APIResponse.fail) sin abrir el restaurante.
# No hay HTTP, no hay BD — solo construimos objetos Pydantic
# y verificamos que tengan exactamente los campos correctos.
#
# ¿Por qué son unitarios?
#   No levantamos la app FastAPI ni tocamos PostgreSQL.
#   Solo importamos los schemas y los instanciamos directamente.
#   Son los tests más rápidos y baratos de ejecutar.
#
# Escenarios cubiertos:
#   ErrorDetail
#     1. Construye con code y message correctos
#     2. Serializa a dict con los campos esperados
#
#   APIResponse.ok
#     3. success=True
#     4. data contiene el objeto recibido
#     5. error es None
#
#   APIResponse.fail
#     6. success=False
#     7. data es None
#     8. error tiene code correcto
#     9. error tiene message correcto
#
#   APIResponse — invariantes estructurales
#    10. ok + fail producen tipos mutuamente excluyentes (data vs error)
#    11. APIResponse[T] funciona con distintos tipos de T
#
# ============================================================

import pytest
from pydantic import BaseModel

from app.schemas.common import APIResponse, ErrorDetail


# ============================================================
# Schema auxiliar de prueba
# ============================================================
# No queremos importar UserResponse ni ProductResponse aquí —
# ese acoplamiento haría que este test fallara si cambia un schema
# de otro módulo. En cambio creamos un schema mínimo propio.
# Esto también demuestra que APIResponse[T] funciona con CUALQUIER
# subclase de BaseModel, no solo con los schemas de BizCore.
class FakeItem(BaseModel):
    """Schema de prueba — representa cualquier recurso de la API."""

    id: int
    name: str


# ============================================================
# Fixture reutilizable — un FakeItem de ejemplo
# ============================================================
@pytest.fixture
def sample_item() -> FakeItem:
    """Ítem de prueba que simula un recurso de la API."""
    return FakeItem(id=1, name="Producto de prueba")


# ============================================================
# ErrorDetail — tests 1–2
# ============================================================
class TestErrorDetail:
    def test_stores_code_and_message(self):
        """
        [1] ErrorDetail guarda correctamente los dos campos.

        Verificamos que el constructor asigna `code` y `message`
        sin modificarlos ni transformarlos.
        """
        error = ErrorDetail(code="not_found", message="El recurso no existe.")

        assert error.code == "not_found"
        assert error.message == "El recurso no existe."

    def test_serializes_to_dict(self):
        """
        [2] ErrorDetail serializa a dict con exactamente los campos esperados.

        model_dump() es el método Pydantic que convierte el objeto a dict.
        Lo que FastAPI envía como JSON es exactamente este dict.
        Verificamos que no haya campos de más ni de menos.
        """
        error = ErrorDetail(code="already_exists", message="Email en uso.")

        result = error.model_dump()

        # Solo deben existir estos dos campos — nada más
        assert result == {"code": "already_exists", "message": "Email en uso."}


# ============================================================
# APIResponse.ok — tests 3–5
# ============================================================
class TestAPIResponseOk:
    def test_success_is_true(self, sample_item: FakeItem):
        """
        [3] APIResponse.ok produce success=True.

        La caja lleva la etiqueta ✅ cuando la operación salió bien.
        """
        response = APIResponse.ok(sample_item)

        assert response.success is True

    def test_data_contains_the_item(self, sample_item: FakeItem):
        """
        [4] APIResponse.ok pone el objeto recibido en el campo data.

        El contenido de la caja debe ser exactamente el ítem que pasamos.
        """
        response = APIResponse.ok(sample_item)

        assert response.data == sample_item

    def test_error_is_none(self, sample_item: FakeItem):
        """
        [5] APIResponse.ok deja error=None.

        Cuando hay éxito no puede haber un error dentro de la caja.
        Verificamos la invariante: data lleno → error vacío.
        """
        response = APIResponse.ok(sample_item)

        assert response.error is None


# ============================================================
# APIResponse.fail — tests 6–9
# ============================================================
class TestAPIResponseFail:
    def test_success_is_false(self):
        """
        [6] APIResponse.fail produce success=False.

        La caja lleva la etiqueta ❌ cuando algo salió mal.
        """
        response = APIResponse.fail("not_found", "Recurso no encontrado.")

        assert response.success is False

    def test_data_is_none(self):
        """
        [7] APIResponse.fail deja data=None.

        Cuando hay error no hay payload de datos.
        Verificamos la invariante: error lleno → data vacío.
        """
        response = APIResponse.fail("not_found", "Recurso no encontrado.")

        assert response.data is None

    def test_error_has_correct_code(self):
        """
        [8] APIResponse.fail pone el code correcto en error.

        El frontend usará error.code para decidir qué hacer.
        Debe coincidir exactamente con el string que pasamos.
        """
        response = APIResponse.fail("already_exists", "Email en uso.")

        assert response.error is not None
        assert response.error.code == "already_exists"

    def test_error_has_correct_message(self):
        """
        [9] APIResponse.fail pone el message correcto en error.

        El mensaje es para mostrarlo al usuario final.
        Debe coincidir exactamente con el string que pasamos.
        """
        response = APIResponse.fail("already_exists", "Email en uso.")

        assert response.error is not None
        assert response.error.message == "Email en uso."


# ============================================================
# Invariantes estructurales — tests 10–11
# ============================================================
class TestAPIResponseInvariants:
    def test_ok_and_fail_are_mutually_exclusive(self, sample_item: FakeItem):
        """
        [10] ok y fail producen campos mutuamente excluyentes.

        En ok:   data tiene valor, error es None
        En fail: data es None,     error tiene valor
        Nunca ambos llenos, nunca ambos vacíos.
        """
        ok_response = APIResponse.ok(sample_item)
        fail_response = APIResponse.fail("error_code", "Algo salió mal.")

        # ok: data lleno, error vacío
        assert ok_response.data is not None
        assert ok_response.error is None

        # fail: data vacío, error lleno
        assert fail_response.data is None
        assert fail_response.error is not None

    def test_works_with_different_item_types(self):
        """
        [11] APIResponse[T] funciona con distintos tipos de T.

        El "hueco en blanco" T puede ser cualquier BaseModel.
        Probamos con dos schemas diferentes para confirmar que
        el genérico no está atado a un tipo específico.
        """

        class AnotherSchema(BaseModel):
            value: float

        item_a = FakeItem(id=99, name="Cosa A")
        item_b = AnotherSchema(value=3.14)

        response_a = APIResponse.ok(item_a)
        response_b = APIResponse.ok(item_b)

        assert response_a.data == item_a
        assert response_b.data == item_b
