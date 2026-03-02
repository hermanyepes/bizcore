# Importar todos los modelos aquí para que SQLAlchemy los registre
# en Base.metadata y pueda crear las tablas correctamente.
# El patrón "X as X" le indica a ruff que el re-export es intencional.
from app.models.inventory_movement import InventoryMovement as InventoryMovement
from app.models.order import Order as Order
from app.models.order import OrderItem as OrderItem
from app.models.product import Product as Product
from app.models.supplier import Supplier as Supplier
from app.models.user import User as User
