"""
Script para crear el usuario administrador inicial de BizCore.

Uso:
    cd backend
    .venv\\Scripts\\activate
    python seed_admin.py
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User


async def create_admin() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Verificar si ya existe
        result = await session.execute(
            select(User).where(User.email == "admin@bizcore.com")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("El usuario admin@bizcore.com ya existe — no se creó nada.")
        else:
            admin = User(
                document_id="1000000000",
                document_type="CC",
                full_name="Administrador BizCore",
                email="admin@bizcore.com",
                role="Administrador",
                password_hash=hash_password("Admin1234"),
                is_active=True,
                join_date=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            session.add(admin)
            await session.commit()
            print("✓ Usuario administrador creado:")
            print("  Email:    admin@bizcore.com")
            print("  Password: Admin1234")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())
