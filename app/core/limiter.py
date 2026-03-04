# ============================================================
# BizCore — Rate Limiter (singleton)
# ============================================================
#
# ANALOGÍA: el limiter es el guardia de la puerta de un banco.
# No le importa si tienes la llave o no — si intentas entrar
# demasiadas veces en poco tiempo, te detiene antes de que
# el portero (el endpoint) siquiera te vea.
#
# ¿POR QUÉ un archivo separado?
# El limiter es un objeto con ESTADO (lleva la cuenta de requests).
# Si lo creáramos en main.py y auth.py lo importara, habría
# un riesgo de importaciones circulares. Al vivir en core/,
# cualquier archivo puede importarlo sin conflictos.
#
# ¿POR QUÉ un solo objeto y no uno por router?
# El estado del límite está en MemoryStorage, que es compartido.
# Un solo limiter con distintos decoradores por endpoint
# es la arquitectura correcta — no necesitamos uno por módulo.
#
# ============================================================

from slowapi import Limiter
from slowapi.util import get_remote_address

# key_func=get_remote_address: el límite se aplica POR IP.
# Cada IP tiene su propio contador independiente.
# Si un atacante usa 10 IPs distintas, cada una tiene su cuota.
#
# MemoryStorage (por defecto): los contadores viven en RAM.
# Ventaja: sin dependencias externas (no necesita Redis).
# Limitación: si el servidor se reinicia, los contadores se resetean.
# Para producción real se usaría Redis, pero para este scope es correcto.
limiter = Limiter(key_func=get_remote_address)
