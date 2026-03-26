# ============================================================
# BizCore — Servicio: lógica de negocio para Suppliers
# ============================================================
#
# ANALOGÍA: este archivo es el chef del área de proveedores.
# El mesero (endpoint) trae el pedido; el chef decide cómo prepararlo:
#   - ¿Ya existe un proveedor con ese nombre? → rechazar.
#   - ¿Ya existe un proveedor con ese email? → rechazar.
#   - ¿El proveedor existe antes de actualizarlo? → verificar.
#
# DIFERENCIA RESPECTO A ProductService:
# Suppliers tiene DOS campos únicos: `name` y `contact_email`.
# Además, `contact_email` es opcional — el proveedor puede no
# tener email registrado. Por eso los checks son condicionales
# tanto en `create` como en `update`.
#
# Tabla de checks por operación:
#
#   create:
#     - name          → siempre (siempre viene en SupplierCreate)
#     - contact_email → solo si data.contact_email is not None
#
#   update:
#     - name          → solo si el cliente lo envió (data.name is not None)
#     - contact_email → solo si el cliente lo envió (data.contact_email is not None)
#     En ambos casos, exclude_id evita el falso positivo del propio registro.
#
# ============================================================

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.crud import supplier as supplier_crud
from app.models.supplier import Supplier
from app.schemas.supplier import (
    SupplierCreate,
    SupplierPaginated,
    SupplierResponse,
    SupplierUpdate,
)
from app.services.validation import check_unique_field


class SupplierService:
    """
    Orquesta todas las operaciones de negocio del módulo de proveedores.

    No recibe db en el constructor — cada método recibe su propia sesión.
    La sesión de BD vive por request, no por instancia de servicio.
    """

    # ============================================================
    # LIST — Listar con paginación y filtro
    # ============================================================

    async def list(
        self,
        db: AsyncSession,
        page: int,
        page_size: int,
        is_active: bool | None,
    ) -> SupplierPaginated:
        """
        Devuelve una página de proveedores con metadatos de paginación.

        Suppliers no tiene filtro por categoría (a diferencia de productos).
        Solo acepta el filtro is_active: True/False/None (todos).
        """
        # Convertir número de página → offset para la query SQL.
        skip = (page - 1) * page_size

        suppliers, total = await supplier_crud.get_suppliers(
            db, skip=skip, limit=page_size, is_active=is_active
        )

        # Evitar división entre 0 si no hay registros.
        pages = math.ceil(total / page_size) if total > 0 else 0

        return SupplierPaginated(
            items=[SupplierResponse.model_validate(s) for s in suppliers],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ============================================================
    # GET — Obtener un proveedor por id
    # ============================================================

    async def get(self, db: AsyncSession, supplier_id: int) -> Supplier:
        """
        Busca un proveedor por su id numérico.

        Lanza NotFoundError si no existe — el manejador global
        en main.py lo convierte en HTTP 404.
        """
        supplier = await supplier_crud.get_supplier_by_id(db, supplier_id)
        if supplier is None:
            raise NotFoundError("Proveedor", supplier_id)
        return supplier

    # ============================================================
    # CREATE — Registrar un nuevo proveedor
    # ============================================================

    async def create(self, db: AsyncSession, data: SupplierCreate) -> Supplier:
        """
        Crea un nuevo proveedor verificando unicidad de nombre y email.

        Reglas de negocio:
        1. name es único en la tabla suppliers → siempre verificar.
        2. contact_email es único en la tabla suppliers, pero es
           opcional — si no viene en el payload, no hay nada que verificar.

        ¿Por qué contact_email puede ser None?
        No todos los proveedores tienen email registrado. El schema
        SupplierCreate declara contact_email como Optional[str].
        """
        # Nombre siempre viene en SupplierCreate → siempre verificar.
        await check_unique_field(db, Supplier, "name", data.name)

        # Email solo viene si el cliente lo incluyó en el payload.
        if data.contact_email is not None:
            await check_unique_field(db, Supplier, "contact_email", data.contact_email)

        return await supplier_crud.create_supplier(db, data)

    # ============================================================
    # UPDATE — Actualizar campos de un proveedor existente
    # ============================================================

    async def update(
        self, db: AsyncSession, supplier_id: int, data: SupplierUpdate
    ) -> Supplier:
        """
        Actualiza solo los campos que el cliente envió.

        Reglas de negocio condicionales (igual que ProductService.update):
        - Si el cliente envió `name` → verificar que no lo use otro proveedor.
        - Si el cliente envió `contact_email` → verificar que no lo use otro.
        - En ambos casos, exclude_id ignora el propio proveedor para no
          generar un 409 falso cuando el valor no cambia.

        Si el proveedor no existe (crud devuelve None) → NotFoundError (404).
        """
        if data.name is not None:
            await check_unique_field(
                db, Supplier, "name", data.name, exclude_id=supplier_id
            )

        if data.contact_email is not None:
            await check_unique_field(
                db,
                Supplier,
                "contact_email",
                data.contact_email,
                exclude_id=supplier_id,
            )

        supplier = await supplier_crud.update_supplier(db, supplier_id, data)
        if supplier is None:
            raise NotFoundError("Proveedor", supplier_id)
        return supplier

    # ============================================================
    # DELETE — Soft delete (desactivar)
    # ============================================================

    async def delete(self, db: AsyncSession, supplier_id: int) -> Supplier:
        """
        Desactiva un proveedor marcando is_active=False.

        ¿Por qué no eliminar el registro?
        Los pedidos (Orders) tienen una FK a suppliers.id. Borrar la
        fila rompería todos los pedidos históricos de ese proveedor.
        Desactivar es seguro, reversible, y conserva la integridad.
        """
        supplier = await supplier_crud.delete_supplier(db, supplier_id)
        if supplier is None:
            raise NotFoundError("Proveedor", supplier_id)
        return supplier


# Instancia única compartida por todos los endpoints.
# SupplierService no tiene estado propio — todos los datos pasan
# por el parámetro `db` de cada método. Es seguro compartirla.
supplier_service = SupplierService()
