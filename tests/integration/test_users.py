from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_list_users_as_admin_success(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
    db: AsyncSession,
):
    """GET /users como admin con paginación devuelve 200 + lista paginada."""
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "pages" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_list_users_without_token_returns_401(client: AsyncClient):
    """GET /users sin token devuelve 401."""
    response = await client.get("/api/v1/users/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_with_pagination_params(
    client: AsyncClient,
    admin_token: str,
    db: AsyncSession,
):
    """GET /users con parámetros de paginación devuelve 200 con página especificada."""
    response = await client.get(
        "/api/v1/users/?page=1&page_size=5",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 5


@pytest.mark.asyncio
async def test_list_users_with_is_active_filter(
    client: AsyncClient,
    admin_token: str,
    db: AsyncSession,
):
    """GET /users?is_active=true devuelve solo usuarios activos."""
    response = await client.get(
        "/api/v1/users/?is_active=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["is_active"] is True


@pytest.mark.asyncio
async def test_list_users_with_role_filter(
    client: AsyncClient,
    admin_token: str,
    db: AsyncSession,
):
    """GET /users?role=Administrador devuelve solo usuarios admin."""
    response = await client.get(
        "/api/v1/users/?role=Administrador",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["role"] == "Administrador"


@pytest.mark.asyncio
async def test_list_users_with_page_out_of_range(
    client: AsyncClient,
    admin_token: str,
):
    """GET /users?page=0 devuelve 422 (page debe ser >= 1)."""
    response = await client.get(
        "/api/v1/users/?page=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_users_with_page_size_exceeds_max(
    client: AsyncClient,
    admin_token: str,
):
    """GET /users?page_size=101 devuelve 422 (page_size máximo es 100)."""
    response = await client.get(
        "/api/v1/users/?page_size=101",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_users_with_page_size_less_than_one(
    client: AsyncClient,
    admin_token: str,
):
    """GET /users?page_size=0 devuelve 422 (page_size debe ser >= 1)."""
    response = await client.get(
        "/api/v1/users/?page_size=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_me_as_authenticated_user_success(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """GET /users/me como usuario autenticado devuelve 200 + perfil."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == admin_user.document_id
    assert data["email"] == admin_user.email
    assert data["role"] == "Administrador"
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_get_me_without_token_returns_401(client: AsyncClient):
    """GET /users/me sin token devuelve 401."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_includes_all_fields(
    client: AsyncClient,
    employee_token: str,
):
    """GET /users/me devuelve todos los campos públicos del usuario."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    required_fields = [
        "document_id",
        "document_type",
        "full_name",
        "email",
        "role",
        "join_date",
        "is_active",
        "created_at",
    ]
    for field in required_fields:
        assert field in data


@pytest.mark.asyncio
async def test_get_me_excludes_password_hash(
    client: AsyncClient,
    admin_token: str,
):
    """GET /users/me NO incluye password_hash en la respuesta."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "password_hash" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_get_user_by_document_id_as_owner_success(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """GET /users/{document_id} como dueño devuelve 200 + datos."""
    response = await client.get(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == admin_user.document_id
    assert data["email"] == admin_user.email


@pytest.mark.asyncio
async def test_get_user_without_token_returns_401(
    client: AsyncClient,
    admin_user: User,
):
    """GET /users/{document_id} sin token devuelve 401."""
    response = await client.get(f"/api/v1/users/{admin_user.document_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_nonexistent_returns_404(
    client: AsyncClient,
    admin_token: str,
):
    """GET /users/{document_id} con ID inexistente devuelve 404."""
    response = await client.get(
        "/api/v1/users/9999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_excludes_password_hash(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """GET /users/{document_id} NO incluye password_hash en respuesta."""
    response = await client.get(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "password_hash" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_create_user_as_admin_success(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users como admin con datos válidos devuelve 201 + usuario creado."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "email": "juan@test.com",
        "phone": "3001234567",
        "city": "Bogotá",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == "1234567890"
    assert data["email"] == "juan@test.com"
    assert data["role"] == "Empleado"
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_create_user_without_token_returns_401(client: AsyncClient):
    """POST /users sin token devuelve 401."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "email": "juan@test.com",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post("/api/v1/users/", json=user_data)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_user_as_non_admin_returns_403(
    client: AsyncClient,
    employee_token: str,
):
    """POST /users como usuario no-admin devuelve 403."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "email": "juan@test.com",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_user_with_missing_required_field_returns_422(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users sin campo obligatorio (email) devuelve 422."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_with_invalid_email_returns_422(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users con email inválido devuelve 422."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "email": "not-an-email",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_with_short_password_returns_422(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users con password < 8 caracteres devuelve 422."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "email": "juan@test.com",
        "role": "Empleado",
        "password": "Short1",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_with_invalid_role_returns_422(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users con role inválido devuelve 422."""
    user_data = {
        "document_id": "1234567890",
        "document_type": "CC",
        "full_name": "Juan Pérez",
        "email": "juan@test.com",
        "role": "Superusuario",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_with_duplicate_document_id_returns_409(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """POST /users con document_id duplicado devuelve 409."""
    user_data = {
        "document_id": admin_user.document_id,
        "document_type": "CC",
        "full_name": "Otro Usuario",
        "email": "otro@test.com",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code in [409, 400]


@pytest.mark.asyncio
async def test_create_user_with_duplicate_email_returns_409(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """POST /users con email duplicado devuelve 409."""
    user_data = {
        "document_id": "9876543210",
        "document_type": "CC",
        "full_name": "Otro Usuario",
        "email": admin_user.email,
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code in [409, 400]


@pytest.mark.asyncio
async def test_create_user_returns_created_resource(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users devuelve el usuario creado con all fields.
    Admin puede crear Empleados y Supervisores (HU-018: no Admin ni Superadmin).
    """
    user_data = {
        "document_id": "5555555555",
        "document_type": "CC",
        "full_name": "Test User",
        "email": "test@example.com",
        "phone": "3001111111",
        "city": "Medellín",
        "role": "Empleado",
        "password": "TestPass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == "5555555555"
    assert data["full_name"] == "Test User"
    assert data["phone"] == "3001111111"
    assert data["city"] == "Medellín"
    assert data["role"] == "Empleado"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_update_user_as_admin_success(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} como admin con datos válidos devuelve 200."""
    update_data = {
        "full_name": "Admin Updated",
        "phone": "3009999999",
    }

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Admin Updated"
    assert data["phone"] == "3009999999"


@pytest.mark.asyncio
async def test_update_user_without_token_returns_401(
    client: AsyncClient,
    admin_user: User,
):
    """PUT /users/{document_id} sin token devuelve 401."""
    update_data = {"full_name": "Updated Name"}

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_as_non_admin_returns_403(
    client: AsyncClient,
    employee_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} como usuario no-admin devuelve 403."""
    update_data = {"full_name": "Hacked Name"}

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_user_nonexistent_returns_404(
    client: AsyncClient,
    admin_token: str,
):
    """PUT /users/{document_id} con ID inexistente devuelve 404."""
    update_data = {"full_name": "Updated Name"}

    response = await client.put(
        "/api/v1/users/9999999999",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user_with_partial_data(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} con solo algunos campos actualiza solo esos."""
    update_data = {"city": "Cali"}

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Cali"
    assert data["email"] == admin_user.email


@pytest.mark.asyncio
async def test_update_user_with_invalid_role_returns_422(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} con role inválido devuelve 422."""
    update_data = {"role": "InvalidRole"}

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_with_short_password_returns_422(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} con password < 8 caracteres devuelve 422."""
    update_data = {"password": "Short"}

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_can_change_role(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
):
    """PUT /users/{document_id} puede cambiar el role del usuario.
    Admin puede promover a Supervisor (HU-018: no puede promover a Admin ni Superadmin).
    """
    update_data = {"role": "Supervisor"}

    response = await client.put(
        f"/api/v1/users/{employee_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "Supervisor"


@pytest.mark.asyncio
async def test_update_user_can_deactivate(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
):
    """PUT /users/{document_id} puede desactivar usuario seteando is_active=false."""
    update_data = {"is_active": False}

    response = await client.put(
        f"/api/v1/users/{employee_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_delete_user_as_admin_success(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
):
    """DELETE /users/{document_id} como admin devuelve 200 + usuario inactivo."""
    response = await client.delete(
        f"/api/v1/users/{employee_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_delete_user_without_token_returns_401(
    client: AsyncClient,
    employee_user: User,
):
    """DELETE /users/{document_id} sin token devuelve 401."""
    response = await client.delete(f"/api/v1/users/{employee_user.document_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_user_as_non_admin_returns_403(
    client: AsyncClient,
    employee_token: str,
    admin_user: User,
):
    """DELETE /users/{document_id} como usuario no-admin devuelve 403."""
    response = await client.delete(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_nonexistent_returns_404(
    client: AsyncClient,
    admin_token: str,
):
    """DELETE /users/{document_id} con ID inexistente devuelve 404."""
    response = await client.delete(
        "/api/v1/users/9999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_soft_deletes_only(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
    db: AsyncSession,
):
    """DELETE /users/{document_id} no elimina registro, solo marca inactivo."""
    response = await client.delete(
        f"/api/v1/users/{employee_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    result = await db.execute(select(User).where(User.document_id == employee_user.document_id))
    user_in_db = result.scalar_one()
    assert user_in_db is not None
    assert user_in_db.is_active is False


@pytest.mark.asyncio
async def test_delete_user_returns_deactivated_user(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
):
    """DELETE /users/{document_id} devuelve el usuario con is_active=False."""
    response = await client.delete(
        f"/api/v1/users/{employee_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == employee_user.document_id
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_list_users_critical_requires_admin(
    client: AsyncClient,
    employee_token: str,
):
    """
    GET /users como usuario no-admin DEBERÍA devolver 403.
    CRÍTICO: list_users actualmente falta require_admin decorator.
    Este test fallará hasta que se agregue @require_admin.
    """
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 403, (
        "list_users debe tener @require_admin. "
        f"Actualmente devuelve {response.status_code}"
    )


@pytest.mark.asyncio
async def test_get_user_critical_validates_authorization(
    client: AsyncClient,
    employee_token: str,
    admin_user: User,
):
    """
    GET /users/{document_id} como usuario diferente al dueño DEBERÍA devolver 403.
    CRÍTICO: get_user actualmente falta validación de autorización.
    Este test fallará hasta que se agregue la validación.
    """
    response = await client.get(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 403, (
        "get_user debe validar que solo el dueño o admin puedan acceder. "
        f"Actualmente devuelve {response.status_code}"
    )


@pytest.mark.asyncio
async def test_create_user_response_excludes_password(
    client: AsyncClient,
    admin_token: str,
):
    """POST /users respuesta NO incluye password o password_hash."""
    user_data = {
        "document_id": "4444444444",
        "document_type": "CC",
        "full_name": "Password Test",
        "email": "pwd@test.com",
        "role": "Empleado",
        "password": "SecurePass123",
    }

    response = await client.post(
        "/api/v1/users/",
        json=user_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_update_user_response_excludes_password(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} respuesta NO incluye password o password_hash."""
    update_data = {"password": "NewSecurePass123"}

    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_superadmin_can_edit_email(
    client: AsyncClient,
    superadmin_token: str,
    employee_user: User,
):
    """PUT /users/{document_id} como Superadmin puede cambiar el email → 200 con email nuevo."""
    response = await client.put(
        f"/api/v1/users/{employee_user.document_id}",
        json={"email": "nuevo@test.com"},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "nuevo@test.com"


@pytest.mark.asyncio
async def test_admin_cannot_edit_email(
    client: AsyncClient,
    admin_token: str,
    employee_user: User,
):
    """PUT /users/{document_id} como Admin: campo email ignorado, el email no cambia."""
    original_email = employee_user.email

    response = await client.put(
        f"/api/v1/users/{employee_user.document_id}",
        json={"email": "hackeado@test.com", "full_name": "Nombre Actualizado"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == original_email
    assert data["full_name"] == "Nombre Actualizado"


@pytest.mark.asyncio
async def test_superadmin_can_hard_delete_inactive_user_without_activity(
    client: AsyncClient,
    superadmin_token: str,
    db: AsyncSession,
):
    """DELETE /users/{document_id}/permanent borra físicamente usuario inactivo sin actividad → 200."""
    target = User(
        document_id="7777777777",
        document_type="CC",
        full_name="Para Borrar",
        email="todelete@test.com",
        role="Empleado",
        password_hash=hash_password("Pass1234"),
        is_active=False,
        join_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)

    response = await client.delete(
        f"/api/v1/users/{target.document_id}/permanent",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )

    assert response.status_code == 200

    result = await db.execute(select(User).where(User.document_id == "7777777777"))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cannot_hard_delete_user_with_orders(
    client: AsyncClient,
    superadmin_token: str,
    admin_user: User,
    order,
):
    """DELETE /users/{document_id}/permanent con órdenes asociadas → 403 con mensaje claro."""
    response = await client.delete(
        f"/api/v1/users/{admin_user.document_id}/permanent",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )

    assert response.status_code == 403
    assert "actividad registrada" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_cannot_edit_peer_admin(
    client: AsyncClient,
    admin_token: str,
    second_admin_user: User,
):
    """PUT /users/{document_id} como Admin sobre otro Admin → 403 (jerarquía estricta)."""
    response = await client.put(
        f"/api/v1/users/{second_admin_user.document_id}",
        json={"full_name": "Hackeado"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403
    assert "Administrador" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_edit_themselves(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} como Admin sobre sí mismo → 200 (autogestión permitida)."""
    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json={"phone": "3001234567"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "3001234567"


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_peer_admin(
    client: AsyncClient,
    admin_token: str,
    second_admin_user: User,
):
    """DELETE /users/{document_id} como Admin sobre otro Admin → 403 (jerarquía estricta)."""
    response = await client.delete(
        f"/api/v1/users/{second_admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403
    assert "igual o superior" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_themselves(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """DELETE /users/{document_id} como Admin sobre su propia cuenta → 403."""
    response = await client.delete(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403
    assert "propia cuenta" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_cannot_change_own_role(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} — Admin no puede cambiar su propio rol (Separation of Duties)."""
    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json={"role": "Supervisor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403
    assert "rol" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_superadmin_can_edit_any_admin(
    client: AsyncClient,
    superadmin_token: str,
    admin_user: User,
):
    """PUT /users/{document_id} como Superadmin sobre un Admin → 200 (sin restricciones)."""
    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        json={"city": "Cali"},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["city"] == "Cali"


@pytest.mark.asyncio
async def test_user_timestamps_are_present(
    client: AsyncClient,
    admin_token: str,
    admin_user: User,
):
    """GET /users/me devuelve timestamps: created_at, updated_at, join_date."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "created_at" in data
    assert "join_date" in data
    assert data["created_at"] is not None
    assert data["join_date"] is not None
