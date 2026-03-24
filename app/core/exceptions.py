# ============================================================
# BizCore — Excepciones de dominio propias
# ============================================================
#
# ANALOGÍA: estas son las "alarmas" del sistema.
# El endpoint (o el servicio) las dispara; el manejador global
# en main.py decide cómo traducirlas a una respuesta HTTP.
#
# JERARQUÍA:
#   BizCoreError (base — no se lanza directamente)
#   ├── NotFoundError          → 404  (recurso no existe)
#   ├── AlreadyExistsError     → 409  (campo único duplicado)
#   ├── InactiveResourceError  → 400  (recurso existe pero está inactivo)
#   └── InsufficientStockError → 400  (stock insuficiente para SALIDA)
#
# ¿POR QUÉ heredar de Exception y NO de HTTPException?
#   HTTPException es una clase de FastAPI — mezclaría la capa de
#   dominio con la capa de transporte HTTP.
#   Una excepción de dominio no sabe si el consumidor es HTTP,
#   un job de fondo, o un CLI. Eso lo decide el manejador.
#
# ¿QUÉ HACE super().__init__(mensaje)?
#   Exception guarda el mensaje internamente. Llamar str(exc) sobre
#   cualquiera de estas excepciones devuelve ese mensaje, lo que
#   permite al manejador construir la respuesta JSON con un simple
#   "detail": str(exc).
#
# ============================================================


class BizCoreError(Exception):
    """Base de todas las excepciones de dominio de BizCore."""
    pass


class NotFoundError(BizCoreError):
    """
    Se lanza cuando un recurso solicitado no existe en la BD.

    Ejemplos:
        raise NotFoundError("Usuario", "1000000001")
        raise NotFoundError("Producto", "42")
        raise NotFoundError("Proveedor", "7")
    """

    def __init__(self, resource: str, identifier: str | int) -> None:
        # resource   → nombre legible del modelo: "Usuario", "Producto", etc.
        # identifier → el id o document_id que no se encontró
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} '{identifier}' no encontrado")


class AlreadyExistsError(BizCoreError):
    """
    Se lanza cuando se intenta crear o actualizar un recurso usando
    un valor de campo único que ya está registrado en otro registro.

    Ejemplos:
        raise AlreadyExistsError("Usuario", "email", "juan@mail.com")
        raise AlreadyExistsError("Producto", "name", "Café Premium")
    """

    def __init__(self, resource: str, field: str, value: str) -> None:
        # resource → nombre del modelo: "Usuario", "Producto", etc.
        # field    → nombre del atributo duplicado: "email", "name", etc.
        # value    → el valor que ya está registrado
        self.resource = resource
        self.field = field
        self.value = value
        super().__init__(f"{resource} con {field}='{value}' ya existe")


class InactiveResourceError(BizCoreError):
    """
    Se lanza cuando se intenta operar sobre un recurso que existe
    en la BD pero está desactivado (is_active=False).

    Ejemplos:
        raise InactiveResourceError("Producto", "Café Molido")
        raise InactiveResourceError("Proveedor", "Distribuidora El Sol")
    """

    def __init__(self, resource: str, name: str) -> None:
        # resource → nombre del modelo: "Producto", "Proveedor", etc.
        # name     → nombre o identificador legible del recurso inactivo
        self.resource = resource
        self.name = name
        super().__init__(f"{resource} '{name}' está inactivo")


class InsufficientStockError(BizCoreError):
    """
    Se lanza cuando una SALIDA o pedido solicita más unidades
    de las que hay disponibles en stock.

    Ejemplos:
        raise InsufficientStockError("Café Molido", available=10, requested=15)
    """

    def __init__(self, product_name: str, available: int, requested: int) -> None:
        # product_name → nombre del producto con stock insuficiente
        # available    → unidades actuales en stock
        # requested    → unidades que se intentaron retirar
        self.product_name = product_name
        self.available = available
        self.requested = requested
        super().__init__(
            f"Stock insuficiente para '{product_name}'. "
            f"Disponible: {available}, solicitado: {requested}"
        )
