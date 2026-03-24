# ============================================================
# BizCore — Tests unitarios: services/validation.py
# ============================================================
#
# ANALOGÍA: probamos al notario en una oficina vacía, con registros
# inventados, sin que el restaurante (la app) esté abierto.
# Solo queremos saber si el notario aplica las tres reglas correctamente.
#
# ¿Por qué son "unitarios" si usan una BD?
#   Técnicamente estos tests tocan SQLite (vía el fixture `db`),
#   pero siguen siendo unitarios porque prueban UNA sola función
#   en aislamiento, sin endpoints HTTP y sin lógica de negocio.
#   El fixture `db` de conftest.py nos da una BD en memoria
#   que desaparece al terminar cada test — cero contaminación entre tests.
#
# Escenarios cubiertos:
#   1. Campo libre → no lanza excepción
#   2. Duplicado en POST (sin exclude_id) → lanza 409
#   3. PUT sobre el mismo registro (exclude_id coincide) → no lanza
#   4. PUT que choca con otro registro (exclude_id diferente) → lanza 409
#   5. pk_field personalizado → funciona con User (PK = document_id)
#   6. Contenido del mensaje 409 → incluye campo y valor
#
# ============================================================

from datetime import UTC, datetime

import pytest

from app.core.exceptions import AlreadyExistsError
from app.core.security import hash_password
from app.models.product import Product
from app.models.user import User
from app.services.validation import check_unique_field

# ============================================================
# Helpers: constructores de modelos de prueba
# ============================================================
# Estas funciones crean registros con los mínimos campos obligatorios.
# Están aquí (y no en conftest.py) porque son específicas de este test.
# ============================================================

def make_product(name: str) -> Product:
    """Crea un Product mínimo para usar en tests de unicidad."""
    return Product(
        name=name,
        description=None,
        price=10000,
        stock=50,
        category="Bebidas",
        is_active=True,
        created_at=datetime.now(UTC),
    )


def make_user(document_id: str, email: str) -> User:
    """Crea un User mínimo para probar pk_field personalizado."""
    return User(
        document_id=document_id,
        document_type="CC",
        full_name="Test User",
        email=email,
        role="Empleado",
        password_hash=hash_password("Test1234"),
        is_active=True,
        join_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


# ============================================================
# Grupo 1: campo libre → no hay conflicto
# ============================================================


async def test_campo_libre_no_lanza_excepcion(db):
    """
    Si ningún registro en la BD tiene ese valor, la función
    debe retornar sin hacer nada (sin lanzar excepción).

    Escenario: BD vacía → cualquier valor está disponible.
    """
    # No insertamos nada → la BD está vacía para este modelo
    # Si la función no lanza, el test pasa automáticamente
    await check_unique_field(db, Product, "name", "Producto Inexistente")


# ============================================================
# Grupo 2: duplicado en POST (sin exclude_id)
# ============================================================


async def test_duplicado_en_create_lanza_already_exists(db):
    """
    Si existe un registro con ese valor y no se pasa exclude_id
    (como en un POST), debe lanzar AlreadyExistsError.

    Escenario: intentar crear un segundo producto "Café"
    cuando ya hay uno en la BD.
    """
    # Arrancar: insertar el producto original
    db.add(make_product("Café"))
    await db.commit()

    # Actuar y verificar: crear sin exclude_id → debe chocar
    with pytest.raises(AlreadyExistsError) as exc_info:
        await check_unique_field(db, Product, "name", "Café")

    # La excepción lleva el campo y el valor para identificar el conflicto
    assert exc_info.value.field == "name"
    assert exc_info.value.value == "Café"


# ============================================================
# Grupo 3: PUT sobre el mismo registro → no es duplicado
# ============================================================


async def test_update_mismo_registro_no_lanza(db):
    """
    En un PUT, si el valor ya pertenece al registro que se edita,
    no debe lanzar excepción (el producto ya tenía ese nombre).

    Escenario: producto "Café" actualiza su precio pero no cambia
    el nombre — el cliente re-envía name="Café".
    """
    # Arrancar: insertar el producto
    producto = make_product("Café")
    db.add(producto)
    await db.commit()
    await db.refresh(producto)  # necesario para leer el id asignado por la BD

    # Actuar: verificar con exclude_id del propio producto
    # El notario encuentra "Café", pero es del mismo registro → ok
    await check_unique_field(db, Product, "name", "Café", exclude_id=producto.id)

    # Sin excepción = correcto


# ============================================================
# Grupo 4: PUT que choca con otro registro
# ============================================================


async def test_update_otro_registro_lanza_409(db):
    """
    En un PUT, si el valor ya lo tiene OTRO registro, debe lanzar 409.

    Escenario: hay dos productos. p2 intenta renombrarse a "Café",
    pero p1 ya tiene ese nombre.
    """
    # Arrancar: dos productos distintos
    p1 = make_product("Café")
    p2 = make_product("Té")
    db.add_all([p1, p2])
    await db.commit()
    await db.refresh(p1)
    await db.refresh(p2)

    # Actuar: p2 quiere renombrarse a "Café" → debe chocar con p1
    with pytest.raises(AlreadyExistsError) as exc_info:
        await check_unique_field(db, Product, "name", "Café", exclude_id=p2.id)

    assert exc_info.value.field == "name"
    assert exc_info.value.value == "Café"


# ============================================================
# Grupo 5: pk_field personalizado (modelo User)
# ============================================================


async def test_pk_field_personalizado_no_lanza_para_mismo_usuario(db):
    """
    Cuando pk_field='document_id', la comparación usa ese campo
    como clave primaria en vez de 'id'.

    Escenario: User no tiene columna 'id' — su PK es 'document_id'.
    Un usuario actualiza su propio email → no debe lanzar.
    """
    # Arrancar: insertar un usuario
    usuario = make_user("1000000001", "juan@empresa.com")
    db.add(usuario)
    await db.commit()

    # Actuar: el mismo usuario actualiza su email sin cambiarlo
    # exclude_id="1000000001" y pk_field="document_id" → debe reconocerse
    await check_unique_field(
        db,
        User,
        "email",
        "juan@empresa.com",
        exclude_id="1000000001",
        pk_field="document_id",
    )

    # Sin excepción = correcto


async def test_pk_field_personalizado_lanza_para_otro_usuario(db):
    """
    Con pk_field='document_id', si el email lo tiene OTRO usuario,
    debe lanzar 409.

    Escenario: dos usuarios. u2 intenta usar el email de u1.
    """
    # Arrancar: dos usuarios con emails distintos
    u1 = make_user("1000000001", "juan@empresa.com")
    u2 = make_user("2000000002", "maria@empresa.com")
    db.add_all([u1, u2])
    await db.commit()

    # Actuar: u2 intenta usar el email de u1 → conflicto
    with pytest.raises(AlreadyExistsError) as exc_info:
        await check_unique_field(
            db,
            User,
            "email",
            "juan@empresa.com",
            exclude_id="2000000002",
            pk_field="document_id",
        )

    assert exc_info.value.field == "email"
    assert exc_info.value.value == "juan@empresa.com"


# ============================================================
# Grupo 6: contenido del mensaje de error
# ============================================================


async def test_mensaje_error_contiene_campo_y_valor(db):
    """
    El mensaje de AlreadyExistsError debe mencionar el campo y el valor
    conflictivo para que el manejador pueda construir una respuesta útil.

    Esto evita mensajes genéricos como "Error de validación" que
    obligan al cliente a adivinar qué salió mal.
    """
    # Arrancar: producto existente
    db.add(make_product("Café"))
    await db.commit()

    # Actuar: provocar el AlreadyExistsError
    with pytest.raises(AlreadyExistsError) as exc_info:
        await check_unique_field(db, Product, "name", "Café")

    # Verificar: los atributos y el str() del error incluyen campo y valor
    assert exc_info.value.field == "name"
    assert exc_info.value.value == "Café"
    assert "name" in str(exc_info.value)
    assert "Café" in str(exc_info.value)
