"""
Script de utilidad para crear todas las tablas en PostgreSQL.
Ejecutar una sola vez cuando la BD no tiene las tablas creadas.

Uso:
    cd backend
    source .venv/Scripts/activate
    python create_tables.py
"""

import asyncio

from app.core.database import Base, engine


async def create_all_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tablas creadas:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_all_tables())
