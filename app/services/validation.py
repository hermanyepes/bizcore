# ============================================================
# BizCore — Utilidades de validación reutilizables
# ============================================================
#
# ANALOGÍA: este módulo es el notario genérico de BizCore.
# Cuando cualquier endpoint necesita verificar que un valor
# no está siendo usado por otro registro en la BD, llama a
# este notario — sin importar si es usuario, producto o proveedor.
#
# ¿Por qué centralizar aquí y no en cada endpoint?
#   Antes de esta función, cada router implementaba su propia
#   versión de "verificar duplicado". El resultado: mensajes de
#   error distintos, lógica de exclude_id diferente en cada archivo,
#   y 8 bloques casi idénticos repartidos en 3 archivos.
#   Si la lógica cambia (ej: el código de error, el formato del
#   mensaje), basta con editar este archivo — todos los endpoints
#   adoptan el cambio automáticamente.
#
# RESPONSABILIDAD DE ESTE MÓDULO:
#   Solo validaciones de unicidad en BD.
#   Las reglas de negocio más complejas (stock, estados, relaciones
#   entre modelos) siguen viviendo en order.py e inventory.py.
#
# ============================================================

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def check_unique_field(
    db: AsyncSession,
    model_class: type,
    field: str,
    value: Any,
    exclude_id: int | str | None = None,
    pk_field: str = "id",
) -> None:
    """
    Verifica que no exista otro registro en la BD con el mismo valor
    en el campo indicado. Si hay conflicto, lanza HTTP 409 Conflict.

    Parámetros:
        db           — sesión de base de datos (AsyncSession de SQLAlchemy)
        model_class  — clase del modelo SQLAlchemy: User, Product, Supplier...
        field        — nombre del atributo a verificar: 'email', 'name', etc.
        value        — valor que se quiere usar para ese campo
        exclude_id   — id del registro que se está editando en un PUT.
                       None en operaciones de creación (POST).
        pk_field     — nombre del atributo que funciona como clave primaria.
                       Por defecto 'id' (Product, Supplier).
                       Usar 'document_id' para el modelo User.

    Comportamiento:
        1. Si no existe ningún registro con ese valor → retorna sin hacer nada
        2. Si existe un registro y es el mismo que se edita → retorna sin hacer nada
        3. Si existe un registro diferente con ese valor → lanza 409 Conflict

    Ejemplos de uso:

        # En un POST (crear): no hay exclude_id
        await check_unique_field(db, Product, "name", data.name)

        # En un PUT (editar): excluir el propio registro del chequeo
        await check_unique_field(db, Product, "name", data.name, exclude_id=product_id)

        # Con User, cuya PK es document_id y no id:
        await check_unique_field(
            db, User, "email", data.email,
            exclude_id=document_id, pk_field="document_id"
        )
    """
    # Construir la query dinámica:
    # SELECT * FROM tabla WHERE campo = valor
    #
    # getattr(model_class, field) es como escribir Product.name o User.email,
    # pero sin saber de antemano qué modelo o campo se va a verificar.
    # Es la pieza clave que hace a esta función genérica.
    query = select(model_class).where(getattr(model_class, field) == value)
    existing = (await db.execute(query)).scalar_one_or_none()

    # Caso 1: ningún registro tiene ese valor → campo disponible, sin conflicto
    if existing is None:
        return

    # Caso 2: existe un registro, pero es el mismo que se está actualizando.
    # Ejemplo: un producto "Café" se actualiza y el cliente vuelve a enviar
    # name="Café" sin cambiarlo. No es un duplicado — es el mismo registro.
    # Solo aplica cuando se pasa exclude_id (operaciones PUT).
    if exclude_id is not None and getattr(existing, pk_field) == exclude_id:
        return

    # Caso 3: existe un registro DIFERENTE con ese valor → conflicto real.
    # Lanzamos 409 Conflict con un mensaje que identifica el campo y el valor
    # para que el cliente sepa exactamente qué está duplicado.
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Ya existe un registro con {field}='{value}'",
    )
