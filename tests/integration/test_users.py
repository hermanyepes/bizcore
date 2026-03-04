# ============================================================
# BizCore — Tests de integración: /api/v1/users (CRUD completo)
# ============================================================
#
# Probamos los 5 endpoints de usuarios:
#
#   GET    /api/v1/users/            → listar (paginado)
#   GET    /api/v1/users/me          → perfil del usuario logueado
#   GET    /api/v1/users/{id}        → obtener uno
#   POST   /api/v1/users/            → crear (solo Administrador)
#   PUT    /api/v1/users/{id}        → actualizar (solo Administrador)
#   DELETE /api/v1/users/{id}        → desactivar (solo Administrador)
#
# Para cada endpoint probamos:
#   ✓ Happy path (funciona bien)
#   ✗ Sin autenticación (→ 401)
#   ✗ Rol insuficiente (→ 403)
#   ✗ Recurso no encontrado (→ 404)
#   ✗ Conflicto de datos (→ 409)
#
# Los fixtures vienen de tests/conftest.py:
#   - client         → cliente HTTP con BD de prueba
#   - admin_user     → usuario Administrador ya en la BD
#   - employee_user  → usuario Empleado ya en la BD
#   - admin_token    → JWT de Administrador
#   - employee_token → JWT de Empleado
#
# ============================================================

import httpx

from app.models.user import User

# Datos de ejemplo para crear un nuevo usuario en los tests
NUEVO_USUARIO = {
    "document_id": "3000000003",
    "document_type": "CC",
    "full_name": "Usuario Nuevo",
    "email": "nuevo@test.com",
    "phone": "3001234567",
    "city": "Bogotá",
    "role": "Empleado",
    "password": "Nuevo1234",
}


# ============================================================
# GET /api/v1/users/ — Listar usuarios
# ============================================================


async def test_listar_usuarios_sin_token_devuelve_401(client: httpx.AsyncClient):
    """
    GET /users sin token debe devolver 401.

    FastAPI intercepta la petición antes de llegar al endpoint:
    oauth2_scheme revisa el header Authorization y rechaza si no está.
    """
    response = await client.get("/api/v1/users/")
    assert response.status_code == 401


async def test_listar_usuarios_con_token_admin(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    GET /users con token válido debe devolver 200 y respuesta paginada.

    Verificamos la estructura: items, total, page, page_size, pages.
    """
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    # Verificar estructura de paginación
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "pages" in data

    # Hay al menos 1 usuario (el admin_user que creamos en el fixture)
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


async def test_listar_usuarios_con_token_empleado(
    client: httpx.AsyncClient, employee_token: str
):
    """
    GET /users con token de Empleado debe devolver 200.

    Listar usuarios NO está restringido a Administrador —
    cualquier usuario autenticado puede ver la lista.
    """
    response = await client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 200


# ============================================================
# GET /api/v1/users/me — Perfil del usuario logueado
# ============================================================


async def test_obtener_perfil_propio_como_admin(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    GET /users/me con token de Administrador debe devolver
    los datos del propio administrador — sin necesitar su document_id.

    Verificamos que los datos del response coinciden con el fixture admin_user.
    """
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    # El response debe coincidir con el usuario cuyo JWT se usó
    assert data["document_id"] == admin_user.document_id
    assert data["email"] == admin_user.email
    assert data["role"] == admin_user.role
    assert data["full_name"] == admin_user.full_name
    # La contraseña nunca debe aparecer
    assert "password_hash" not in data
    assert "password" not in data


async def test_obtener_perfil_propio_como_empleado(
    client: httpx.AsyncClient, employee_token: str, employee_user: User
):
    """
    GET /users/me con token de Empleado también debe devolver 200.

    /me no requiere Administrador — cualquier usuario autenticado
    tiene derecho a ver su propio perfil.
    """
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["document_id"] == employee_user.document_id
    assert data["role"] == "Empleado"


async def test_obtener_perfil_propio_sin_token_devuelve_401(client: httpx.AsyncClient):
    """
    GET /users/me sin token debe devolver 401.

    Sin JWT, get_current_user no puede identificar al usuario
    y lanza HTTPException(401) antes de llegar al endpoint.
    """
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


# ============================================================
# GET /api/v1/users/{document_id} — Obtener un usuario
# ============================================================


async def test_obtener_usuario_existente(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    GET /users/{id} con un document_id que existe debe devolver 200
    y los datos del usuario.
    """
    response = await client.get(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["document_id"] == admin_user.document_id
    assert data["email"] == admin_user.email
    assert data["role"] == admin_user.role
    # La contraseña NUNCA debe aparecer en la respuesta
    assert "password_hash" not in data
    assert "password" not in data


async def test_obtener_usuario_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """
    GET /users/{id} con un document_id que NO existe debe devolver 404.

    ¿Por qué 404 y no 400?
    400 = los datos enviados son malformados
    404 = los datos son válidos pero el recurso no existe
    """
    response = await client.get(
        "/api/v1/users/99999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_obtener_usuario_sin_token_devuelve_401(client: httpx.AsyncClient):
    """GET /users/{id} sin token debe devolver 401."""
    response = await client.get("/api/v1/users/1000000001")
    assert response.status_code == 401


# ============================================================
# POST /api/v1/users/ — Crear usuario
# ============================================================


async def test_crear_usuario_como_admin_devuelve_201(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    POST /users con token de Administrador debe crear el usuario
    y devolver 201 Created con los datos del nuevo usuario.
    """
    response = await client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=NUEVO_USUARIO,
    )

    assert response.status_code == 201

    data = response.json()
    assert data["document_id"] == NUEVO_USUARIO["document_id"]
    assert data["email"] == NUEVO_USUARIO["email"]
    assert data["full_name"] == NUEVO_USUARIO["full_name"]
    assert data["is_active"] is True
    # Verificar que la contraseña NO aparece en la respuesta
    assert "password_hash" not in data
    assert "password" not in data


async def test_crear_usuario_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str
):
    """
    POST /users con token de Empleado debe devolver 403 Forbidden.

    Solo los Administradores pueden crear usuarios.
    """
    response = await client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {employee_token}"},
        json=NUEVO_USUARIO,
    )
    assert response.status_code == 403


async def test_crear_usuario_sin_token_devuelve_401(client: httpx.AsyncClient):
    """POST /users sin token debe devolver 401."""
    response = await client.post("/api/v1/users/", json=NUEVO_USUARIO)
    assert response.status_code == 401


async def test_crear_usuario_email_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    POST /users con un email que ya existe en la BD debe devolver 409 Conflict.

    ¿Por qué 409 y no 400?
    400 = los datos están malformados
    409 = los datos son válidos pero generan un conflicto con el estado actual
    """
    # Intentar crear un usuario con el mismo email que admin_user
    usuario_duplicado = NUEVO_USUARIO.copy()
    usuario_duplicado["email"] = admin_user.email  # email duplicado
    usuario_duplicado["document_id"] = "8888888888"  # document_id diferente

    response = await client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=usuario_duplicado,
    )
    assert response.status_code == 409


async def test_crear_usuario_document_id_duplicado_devuelve_409(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    POST /users con un document_id que ya existe debe devolver 409.
    """
    usuario_duplicado = NUEVO_USUARIO.copy()
    usuario_duplicado["document_id"] = admin_user.document_id  # ID duplicado
    usuario_duplicado["email"] = "otro@test.com"  # email diferente

    response = await client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=usuario_duplicado,
    )
    assert response.status_code == 409


async def test_crear_usuario_datos_invalidos_devuelve_422(
    client: httpx.AsyncClient, admin_token: str
):
    """
    POST /users con datos inválidos (email malformado, rol inválido)
    debe devolver 422 — Pydantic rechaza antes de llegar al endpoint.
    """
    usuario_invalido = NUEVO_USUARIO.copy()
    usuario_invalido["email"] = "esto-no-es-email"
    usuario_invalido["role"] = "Superusuario"  # rol no permitido

    response = await client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=usuario_invalido,
    )
    assert response.status_code == 422


# ============================================================
# PUT /api/v1/users/{document_id} — Actualizar usuario
# ============================================================


async def test_actualizar_usuario_como_admin(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    PUT /users/{id} con token de Administrador debe actualizar
    solo los campos enviados y devolver 200 con los datos actualizados.
    """
    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"phone": "3009998877", "city": "Medellín"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["phone"] == "3009998877"
    assert data["city"] == "Medellín"
    # El resto de campos no cambia
    assert data["email"] == admin_user.email
    assert data["document_id"] == admin_user.document_id


async def test_actualizar_usuario_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """PUT /users/{id} con document_id inexistente debe devolver 404."""
    response = await client.put(
        "/api/v1/users/99999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"phone": "3001234567"},
    )
    assert response.status_code == 404


async def test_actualizar_usuario_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str, admin_user: User
):
    """PUT /users/{id} con token de Empleado debe devolver 403."""
    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {employee_token}"},
        json={"phone": "3001234567"},
    )
    assert response.status_code == 403


# ============================================================
# DELETE /api/v1/users/{document_id} — Desactivar usuario (soft delete)
# ============================================================


async def test_desactivar_usuario_como_admin(
    client: httpx.AsyncClient, admin_token: str, employee_user: User
):
    """
    DELETE /users/{id} con token de Administrador debe:
    - Devolver 200 (no 204 — devolvemos el usuario actualizado)
    - Marcar is_active=False (soft delete, no elimina el registro)
    """
    response = await client.delete(
        f"/api/v1/users/{employee_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["document_id"] == employee_user.document_id
    assert data["is_active"] is False  # soft delete confirmado


async def test_desactivar_usuario_inexistente_devuelve_404(
    client: httpx.AsyncClient, admin_token: str
):
    """DELETE /users/{id} con document_id inexistente debe devolver 404."""
    response = await client.delete(
        "/api/v1/users/99999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


async def test_desactivar_usuario_como_empleado_devuelve_403(
    client: httpx.AsyncClient, employee_token: str, employee_user: User
):
    """DELETE /users/{id} con token de Empleado debe devolver 403."""
    response = await client.delete(
        f"/api/v1/users/{employee_user.document_id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert response.status_code == 403


async def test_desactivar_usuario_sin_token_devuelve_401(client: httpx.AsyncClient):
    """DELETE /users/{id} sin token debe devolver 401."""
    response = await client.delete("/api/v1/users/1000000001")
    assert response.status_code == 401


# ============================================================
# Validación de parámetros de paginación
# ============================================================


async def test_updated_at_se_llena_despues_de_actualizar(
    client: httpx.AsyncClient, admin_token: str, admin_user: User
):
    """
    Después de un PUT, updated_at debe aparecer en el response (no ser null).

    Al crear: updated_at=None (nunca fue actualizado).
    Al hacer PUT: updated_at=<timestamp actual>.
    """
    response = await client.put(
        f"/api/v1/users/{admin_user.document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"city": "Cali"},
    )

    assert response.status_code == 200
    data = response.json()
    # updated_at debe estar presente y no ser null
    assert data["updated_at"] is not None


async def test_filtrar_usuarios_por_rol(
    client: httpx.AsyncClient, admin_token: str, admin_user: User, employee_user: User
):
    """
    GET /users?role=Administrador debe devolver solo los administradores.

    La BD de prueba tiene exactamente un admin y un empleado.
    Filtrar por role=Administrador debe devolver solo uno.
    """
    response = await client.get(
        "/api/v1/users/?role=Administrador",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["role"] == "Administrador"


async def test_filtrar_usuarios_activos(
    client: httpx.AsyncClient, admin_token: str, admin_user: User, employee_user: User
):
    """
    GET /users?is_active=true debe devolver solo los usuarios activos.
    Ambos fixtures son activos, así que el total debe ser 2.
    """
    response = await client.get(
        "/api/v1/users/?is_active=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["is_active"] is True


async def test_listar_usuarios_page_cero_devuelve_422(
    client: httpx.AsyncClient, admin_token: str
):
    """
    GET /users?page=0 debe devolver 422.

    Query(ge=1) le dice a Pydantic que el mínimo es 1.
    page=0 viola esa restricción → Pydantic rechaza antes del endpoint.
    """
    response = await client.get(
        "/api/v1/users/?page=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_listar_usuarios_page_size_cero_devuelve_422(
    client: httpx.AsyncClient, admin_token: str
):
    """GET /users?page_size=0 debe devolver 422 (mínimo es 1)."""
    response = await client.get(
        "/api/v1/users/?page_size=0",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422


async def test_listar_usuarios_page_size_excesivo_devuelve_422(
    client: httpx.AsyncClient, admin_token: str
):
    """GET /users?page_size=101 debe devolver 422 (máximo es 100)."""
    response = await client.get(
        "/api/v1/users/?page_size=101",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422
