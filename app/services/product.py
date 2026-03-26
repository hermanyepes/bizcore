# ============================================================
# BizCore — Servicio: lógica de negocio para Products
# ============================================================
#
# ANALOGÍA: este archivo es el chef del área de productos.
# El mesero (endpoint) trae el pedido; el chef decide cómo prepararlo:
#   - ¿Ya existe un producto con ese nombre? → rechazar antes de insertar.
#   - ¿El producto existe antes de actualizarlo? → verificar.
#   - ¿El cliente quiere renombrar? → verificar que el nuevo nombre
#     no esté ocupado por OTRO producto (no por él mismo).
#
# DIFERENCIA CLAVE RESPECTO A UserService:
# En `update`, el check de unicidad es condicional — solo se ejecuta
# si el cliente envió el campo `name`. Además, usa `exclude_id` para
# no chocar con el propio producto que se está editando.
#
# Ejemplo de por qué importa exclude_id:
#   Producto id=5, name="Café Premium"
#   Cliente envía PUT /products/5  con {"name": "Café Premium", "price": 30000}
#   Sin exclude_id → check_unique_field encontraría el propio producto → 409
#   Con exclude_id=5 → ignora el registro id=5 → sin conflicto → 200 ✓
#
# ============================================================

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.crud import product as product_crud
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductPaginated,
    ProductResponse,
    ProductUpdate,
)
from app.services.validation import check_unique_field


class ProductService:
    """
    Orquesta todas las operaciones de negocio del módulo de productos.

    No recibe db en el constructor — cada método recibe su propia sesión.
    La sesión de BD vive por request, no por instancia de servicio.
    """

    # ============================================================
    # LIST — Listar con paginación y filtros
    # ============================================================

    async def list(
        self,
        db: AsyncSession,
        page: int,
        page_size: int,
        is_active: bool | None,
        category: str | None,
    ) -> ProductPaginated:
        """
        Devuelve una página de productos con metadatos de paginación.

        ¿Por qué el cálculo de skip y pages vive aquí?
        Es lógica de dominio de paginación — no responsabilidad del
        contrato HTTP. El endpoint solo pasa los parámetros que llegaron
        en la query string; el servicio decide cómo usarlos.
        """
        # Convertir número de página → offset para la query SQL.
        # Página 1 → skip 0. Página 2 → skip N. Etc.
        skip = (page - 1) * page_size

        products, total = await product_crud.get_products(
            db, skip=skip, limit=page_size, is_active=is_active, category=category
        )

        # Evitar división entre 0 si no hay registros.
        pages = math.ceil(total / page_size) if total > 0 else 0

        return ProductPaginated(
            items=[ProductResponse.model_validate(p) for p in products],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ============================================================
    # GET — Obtener un producto por id
    # ============================================================

    async def get(self, db: AsyncSession, product_id: int) -> Product:
        """
        Busca un producto por su id numérico.

        Lanza NotFoundError si no existe — el manejador global
        en main.py lo convierte en HTTP 404.

        ¿Por qué product_id es int y document_id era str?
        Product usa id autoincremental (entero) como PK.
        User usa document_id (string) como PK.
        La firma del método refleja el tipo real de la BD.
        """
        product = await product_crud.get_product_by_id(db, product_id)
        if product is None:
            raise NotFoundError("Producto", product_id)
        return product

    # ============================================================
    # CREATE — Registrar un nuevo producto
    # ============================================================

    async def create(self, db: AsyncSession, data: ProductCreate) -> Product:
        """
        Crea un nuevo producto verificando unicidad del nombre.

        Regla de negocio: el nombre del producto es único en el catálogo.
        Si ya existe otro producto con ese nombre → AlreadyExistsError (409).

        ¿Por qué solo verificar name y no otros campos?
        Solo `name` tiene restricción UNIQUE en la tabla products.
        price, stock, category son campos libres — pueden repetirse.
        """
        # Verificar que no exista otro producto con el mismo nombre.
        # Product usa 'id' como PK (entero autoincremental) → pk_field por defecto.
        await check_unique_field(db, Product, "name", data.name)

        return await product_crud.create_product(db, data)

    # ============================================================
    # UPDATE — Actualizar campos de un producto existente
    # ============================================================

    async def update(
        self, db: AsyncSession, product_id: int, data: ProductUpdate
    ) -> Product:
        """
        Actualiza solo los campos que el cliente envió.

        Regla de negocio condicional:
        - Si el cliente NO envió `name` → no hay nada que verificar.
        - Si el cliente SÍ envió `name` → verificar que no esté ocupado
          por OTRO producto distinto al que se está editando.

        ¿Por qué exclude_id=product_id?
        Sin él, si el cliente envía el mismo nombre que ya tenía el
        producto (ej: solo quiere cambiar el precio), check_unique_field
        encontraría el propio producto y lanzaría un 409 falso.
        exclude_id le dice: "ignora el registro con id=product_id".
        """
        # Solo verificar unicidad de nombre si el cliente lo envió.
        if data.name is not None:
            await check_unique_field(
                db, Product, "name", data.name, exclude_id=product_id
            )

        product = await product_crud.update_product(db, product_id, data)
        if product is None:
            raise NotFoundError("Producto", product_id)
        return product

    # ============================================================
    # DELETE — Soft delete (desactivar)
    # ============================================================

    async def delete(self, db: AsyncSession, product_id: int) -> Product:
        """
        Desactiva un producto marcando is_active=False.

        ¿Por qué no eliminar el registro?
        Los módulos de inventario y órdenes tienen registros históricos
        que referencian este producto. Borrarlo rompería la integridad
        referencial. Desactivar es seguro, reversible, y auditable.
        """
        product = await product_crud.delete_product(db, product_id)
        if product is None:
            raise NotFoundError("Producto", product_id)
        return product


# Instancia única compartida por todos los endpoints.
# ProductService no tiene estado propio — todos los datos pasan
# por el parámetro `db` de cada método. Es seguro compartirla.
product_service = ProductService()
