# ============================================================
# BizCore — Servicio: lógica de negocio para Users
# ============================================================
#
# ANALOGÍA: este archivo es el chef de la cocina de usuarios.
# El mesero (endpoint) solo recibe el pedido y lo trae a la mesa.
# El chef (UserService) decide cómo prepararlo:
#   - ¿Ya existe ese email? → rechazar antes de tocar la BD.
#   - ¿El usuario existe antes de actualizarlo? → verificar.
#   - ¿Cuántas páginas hay? → calcularlo aquí, no en el endpoint.
#
# ¿POR QUÉ UNA CLASE Y NO FUNCIONES SUELTAS?
# Los servicios de orders e inventory usan funciones sueltas
# porque cada uno tiene una única operación compleja.
# UserService agrupa 5 operaciones relacionadas (list, get, create,
# update, delete). Una clase las mantiene juntas y permite que
# los tests instancien un único objeto para cubrir todos los casos.
#
# ¿POR QUÉ NO LANZAR HTTPException AQUÍ?
# Este servicio no sabe si el consumidor es un endpoint HTTP,
# un job programado, o una CLI. Las excepciones de dominio
# (NotFoundError, AlreadyExistsError) son neutrales — el manejador
# global en main.py las convierte a respuestas HTTP.
#
# FLUJO COMPLETO (ejemplo: create):
#   1. Endpoint recibe POST /users con UserCreate
#   2. Endpoint llama a user_service.create(db, data)
#   3. UserService verifica unicidad con check_unique_field
#   4. UserService llama a user_crud.create_user(db, data)
#   5. user_crud construye el User, hace commit, devuelve el objeto
#   6. UserService devuelve el User al endpoint
#   7. Endpoint serializa con UserResponse y responde 201
#
# ============================================================

import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.crud import user as user_crud
from app.models.inventory_movement import InventoryMovement
from app.models.order import Order
from app.models.user import User
from app.schemas.user import UserCreate, UserPaginated, UserResponse, UserUpdate
from app.services.validation import check_unique_field


class UserService:
    """
    Orquesta todas las operaciones de negocio del módulo de usuarios.

    No recibe db en el constructor — cada método recibe su propia
    sesión. Esto es el patrón estándar en FastAPI: la sesión de BD
    vive por request, no por instancia de servicio.
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
        role: str | None,
    ) -> UserPaginated:
        """
        Devuelve una página de usuarios con metadatos de paginación.

        ¿Por qué el cálculo de skip y pages vive aquí y no en el endpoint?
        skip = (page - 1) * page_size es lógica de dominio de paginación,
        no una responsabilidad del contrato HTTP. Si mañana se agrega
        un CLI que lista usuarios, este cálculo no habría que repetirlo.

        ¿Qué devuelve UserPaginated?
        Un schema Pydantic con: items, total, page, page_size, pages.
        El endpoint lo recibe listo para serializar a JSON.
        """
        # Convertir número de página → offset para la query SQL.
        # Página 1 → skip 0 (los primeros N registros).
        # Página 2 → skip N (saltarse los primeros N).
        skip = (page - 1) * page_size

        users, total = await user_crud.get_users(
            db, skip=skip, limit=page_size, is_active=is_active, role=role
        )

        # math.ceil redondea hacia arriba: 11 usuarios / 10 por página = 2 páginas.
        # Si total=0 evitamos división entre 0.
        pages = math.ceil(total / page_size) if total > 0 else 0

        return UserPaginated(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ============================================================
    # GET — Obtener un usuario por document_id
    # ============================================================

    async def get(self, db: AsyncSession, document_id: str) -> User:
        """
        Busca un usuario por su número de documento.

        Lanza NotFoundError si no existe — el manejador global
        en main.py lo convierte en HTTP 404.

        ¿Por qué devolver User (el modelo) y no UserResponse (schema)?
        El endpoint decide cómo serializar. Devolver el modelo ORM
        le da al endpoint la libertad de usar cualquier schema de respuesta
        sin que el servicio tenga que conocer todos los posibles formatos.
        """
        user = await user_crud.get_user_by_id(db, document_id)
        if user is None:
            raise NotFoundError("Usuario", document_id)
        return user

    # ============================================================
    # CREATE — Crear un nuevo usuario
    # ============================================================

    async def create(self, db: AsyncSession, data: UserCreate) -> User:
        """
        Crea un nuevo usuario verificando unicidad antes de insertar.

        Reglas de negocio aplicadas:
        1. email debe ser único en la tabla users
        2. document_id (PK) debe ser único en la tabla users

        ¿Por qué verificar ambos campos?
        email tiene un índice UNIQUE en PostgreSQL — si no verificamos,
        un duplicado lanzaría un IntegrityError genérico de SQLAlchemy,
        que FastAPI convertiría en un 500. Verificar antes nos da control
        del mensaje de error y el código de respuesta (409 Conflict).

        document_id es la PK — también tiene restricción UNIQUE.
        Mismo motivo: mejor un 409 claro que un 500 genérico.

        pk_field="document_id" le indica a check_unique_field cuál es
        la columna PK de User (no es 'id' como en los demás modelos).
        """
        # Verificar que el email no esté registrado en otro usuario.
        await check_unique_field(db, User, "email", data.email, pk_field="document_id")

        # Verificar que el número de documento no esté ya registrado.
        await check_unique_field(
            db, User, "document_id", data.document_id, pk_field="document_id"
        )

        return await user_crud.create_user(db, data)

    # ============================================================
    # UPDATE — Actualizar campos de un usuario existente
    # ============================================================

    async def update(
        self, db: AsyncSession, document_id: str, data: UserUpdate
    ) -> User:
        """
        Actualiza solo los campos que el cliente envió.

        Si el payload incluye `email` (campo exclusivo de UserUpdateSuperadmin),
        verifica unicidad excluyendo al propio usuario antes de actualizar.
        """
        update_fields = data.model_dump(exclude_unset=True)
        if "email" in update_fields and update_fields["email"] is not None:
            await check_unique_field(
                db, User, "email", update_fields["email"],
                exclude_id=document_id, pk_field="document_id",
            )

        user = await user_crud.update_user(db, document_id, data)
        if user is None:
            raise NotFoundError("Usuario", document_id)
        return user

    # ============================================================
    # HARD DELETE — Borrado físico (solo Superadmin, sin actividad)
    # ============================================================

    async def hard_delete(self, db: AsyncSession, document_id: str) -> User:
        """
        Elimina físicamente un usuario de la BD.

        Condiciones previas verificadas:
        1. El usuario existe (404 si no).
        2. No tiene órdenes ni movimientos de inventario asociados
           (403 con mensaje claro si los tiene).

        Los refresh tokens se revocan por CASCADE automáticamente.
        El objeto User devuelto es el snapshot en memoria antes del borrado.
        """
        user = await user_crud.get_user_by_id(db, document_id)
        if user is None:
            raise NotFoundError("Usuario", document_id)

        orders_count = (
            await db.execute(
                select(func.count()).where(Order.created_by_id == document_id)
            )
        ).scalar_one()

        movements_count = (
            await db.execute(
                select(func.count()).where(
                    InventoryMovement.created_by_id == document_id
                )
            )
        ).scalar_one()

        if orders_count > 0 or movements_count > 0:
            raise PermissionDeniedError(
                "El usuario tiene actividad registrada. Usa desactivar en su lugar."
            )

        deleted = await user_crud.hard_delete_user(db, document_id)
        if deleted is None:
            raise NotFoundError("Usuario", document_id)
        return deleted

    # ============================================================
    # DELETE — Soft delete (desactivar)
    # ============================================================

    async def delete(self, db: AsyncSession, document_id: str) -> User:
        """
        Desactiva un usuario marcando is_active=False.

        No elimina el registro de la BD (soft delete). El crud
        ya implementa esta lógica; el servicio solo verifica que
        el usuario existía antes de intentar desactivarlo.

        ¿Por qué soft delete?
        Si el usuario tiene órdenes o movimientos de inventario
        asociados, borrar el registro rompería la integridad referencial.
        Desactivar es seguro, reversible, y conserva la historia.
        """
        user = await user_crud.delete_user(db, document_id)
        if user is None:
            raise NotFoundError("Usuario", document_id)
        return user


# Instancia única compartida por todos los endpoints.
# FastAPI importa este objeto — no instancia UserService en cada request.
# Es seguro porque UserService no tiene estado propio (no guarda datos
# entre llamadas — todo pasa por el parámetro `db` de cada método).
user_service = UserService()
