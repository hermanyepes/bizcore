"""
Script para crear el usuario administrador inicial de BizCore.

Uso:
    cd backend
    .venv\\Scripts\\activate
    python -m scripts.seed_admin

Variables de entorno:
    BIZCORE_ADMIN_PASSWORD  Si está definida, se usa como contraseña del admin.
                            Si no, se genera una aleatoria con secrets.token_urlsafe(16).
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User


async def create_admin() -> None:
    # Leer la contraseña desde el entorno o generar una aleatoria
    password = os.environ.get("BIZCORE_ADMIN_PASSWORD") or secrets.token_urlsafe(16)

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
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
                role="Superadmin",
                password_hash=hash_password(password),
                is_active=True,
                must_change_password=True,
                join_date=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            session.add(admin)
            await session.commit()
            print("=" * 60)
            print("✓ Usuario administrador creado exitosamente.")
            print("  Email:    admin@bizcore.com")
            print(f"  Password: {password}")
            print("  CÓPIALA AHORA — no se mostrará otra vez.")
            print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())
