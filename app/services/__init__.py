"""
Capa de servicios: orquestación de lógica de negocio.

ANALOGÍA: si el CRUD es un empleado de bodega que mueve cajas sin pensar,
el servicio es el supervisor que decide QUÉ cajas mover, en qué orden,
y qué hacer si algo sale mal.

Usar un servicio cuando la operación:
  - Modifica más de un modelo en la misma transacción
    (ej: crear una orden Y decrementar stock al mismo tiempo)
  - Requiere validar reglas de negocio antes de persistir
    (ej: no se puede crear movimiento de salida si stock < cantidad)
  - Necesita calcular valores derivados que el router no debería calcular
    (ej: precio_unitario snapshot al momento de la orden)

NO usar un servicio cuando:
  - La operación toca un solo modelo sin reglas adicionales
  - El router puede llamar al CRUD directamente sin lógica intermedia

Módulos CON servicio (lógica de negocio compleja):
  - inventory  → valida stock antes de registrar movimientos
  - order      → crea orden + ítems + decrementa stock en una transacción

Módulos SIN servicio (CRUD directo desde el router):
  - user       → operaciones simples sobre un solo modelo
  - product    → ídem
  - supplier   → ídem
"""
