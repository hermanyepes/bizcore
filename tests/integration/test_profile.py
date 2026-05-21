# ============================================================
# BizCore — Tests de integración: perfil de usuario y force-logout
#
# Cubre:
#   PUT  /api/v1/users/me          — editar propio perfil (HU-019)
#   POST /api/v1/auth/change-password  — cambiar contraseña (HU-019 / HU-005)
#   POST /api/v1/users/{id}/force-logout — cierre remoto de sesión (HU-009)
# ============================================================

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.refresh_token import RefreshToken
from app.models.user import User


# ============================================================
# PUT /api/v1/users/me — Editar propio perfil
# ============================================================


@pytest.mark.asyncio
async def test_update_me_full_name_returns_200(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/me con full_name válido devuelve 200 con datos actualizados."""
    response = await client.put(
        "/api/v1/users/me",
        json={"full_name": "Admin Renombrado"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Admin Renombrado"
    assert data["document_id"] == admin_user.document_id


@pytest.mark.asyncio
async def test_update_me_phone_and_city(
    client: AsyncClient,
    admin_token: str,
):
    """PUT /users/me actualiza phone y city correctamente."""
    response = await client.put(
        "/api/v1/users/me",
        json={"phone": "3001234567", "city": "Medellín"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "3001234567"
    assert data["city"] == "Medellín"


@pytest.mark.asyncio
async def test_update_me_without_token_returns_401(client: AsyncClient):
    """PUT /users/me sin token devuelve 401."""
    response = await client.put("/api/v1/users/me", json={"full_name": "X"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_me_empty_body_returns_200(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/me con body vacío no cambia nada — idempotente."""
    response = await client.put(
        "/api/v1/users/me",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["document_id"] == admin_user.document_id


# ============================================================
# POST /api/v1/auth/change-password — Cambiar contraseña
# ============================================================


@pytest.mark.asyncio
async def test_change_password_success_returns_200(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    admin_refresh_token: str,
    db: AsyncSession,
):
    """
    POST /auth/change-password con contraseña actual correcta:
    - Devuelve 200
    - Invalida TODOS los refresh tokens del usuario
    - El refresh token antiguo ya no sirve para renovar
    """
    response = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "TestAdmin@42",  # pragma: allowlist secret
            "new_password": "NuevaPass@99",  # pragma: allowlist secret
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert "message" in response.json()

    # El refresh token anterior debe haber sido revocado
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == admin_user.document_id,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    active_tokens = result.scalars().all()
    assert len(active_tokens) == 0, "Debería no quedar ningún refresh token activo"


@pytest.mark.asyncio
async def test_change_password_wrong_current_returns_401(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """POST /auth/change-password con contraseña actual incorrecta devuelve 401."""
    response = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "ContraseñaIncorrecta",  # pragma: allowlist secret
            "new_password": "NuevaPass@99",  # pragma: allowlist secret
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 401
    assert "Contraseña actual incorrecta" in response.json()["detail"]


@pytest.mark.asyncio
async def test_change_password_new_too_short_returns_422(
    client: AsyncClient,
    admin_token: str,
):
    """POST /auth/change-password con nueva contraseña < 8 chars devuelve 422."""
    response = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "TestAdmin@42",  # pragma: allowlist secret
            "new_password": "corta",  # pragma: allowlist secret
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_change_password_without_token_returns_401(client: AsyncClient):
    """POST /auth/change-password sin token devuelve 401."""
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "TestAdmin@42", "new_password": "NuevaPass@99"},  # pragma: allowlist secret
    )
    assert response.status_code == 401


# ============================================================
# POST /api/v1/users/{id}/force-logout — Cierre remoto de sesión
# ============================================================


@pytest.mark.asyncio
async def test_admin_can_force_logout_employee(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
    admin_user: User,
    db: AsyncSession,
):
    """
    Admin puede forzar el logout de un Empleado:
    - Devuelve 200
    - Todos los refresh tokens del empleado quedan revocados
    """
    # Crear un refresh token para el empleado directamente en BD
    from datetime import timedelta, UTC, datetime
    from app.core.security import hash_refresh_token
    raw = "token-del-empleado-para-force-logout"
    token = RefreshToken(
        user_id=employee_user.document_id,
        token_hash=hash_refresh_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        is_revoked=False,
    )
    db.add(token)
    await db.commit()

    response = await client.post(
        f"/api/v1/users/{employee_user.document_id}/force-logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert "message" in response.json()

    # Verificar que el token fue revocado
    await db.refresh(token)
    assert token.is_revoked is True


@pytest.mark.asyncio
async def test_supervisor_cannot_force_logout(
    client: AsyncClient,
    supervisor_token: str,
    employee_user: User,
):
    """Supervisor no puede forzar el logout — requiere Admin o Superadmin."""
    response = await client.post(
        f"/api/v1/users/{employee_user.document_id}/force-logout",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_force_logout_another_admin(
    client: AsyncClient,
    admin_token: str,
    second_admin_user: User,
):
    """Admin no puede forzar el logout de otro Admin — jerarquía HU-018."""
    response = await client.post(
        f"/api/v1/users/{second_admin_user.document_id}/force-logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_force_logout_nonexistent_user_returns_404(
    client: AsyncClient,
    admin_token: str,
):
    """Force-logout de un usuario que no existe devuelve 404."""
    response = await client.post(
        "/api/v1/users/99999999/force-logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_force_logout_without_token_returns_401(
    client: AsyncClient,
    employee_user: User,
):
    """Force-logout sin token devuelve 401."""
    response = await client.post(
        f"/api/v1/users/{employee_user.document_id}/force-logout",
    )
    assert response.status_code == 401
