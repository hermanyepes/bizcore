# BizCore — Business Management API

A RESTful backend for managing the core operations of a small business: users, products, inventory, suppliers, purchase orders, and a summary dashboard.

Built with **FastAPI**, **SQLAlchemy 2.0 async**, and **PostgreSQL** — fully async from HTTP layer to database.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL + asyncpg driver |
| Migrations | Alembic |
| Authentication | JWT (python-jose) + bcrypt |
| Validation | Pydantic v2 |
| Configuration | pydantic-settings + `.env` |
| Testing | pytest + pytest-asyncio + httpx + SQLite in-memory |
| Linting | ruff |

---

## Modules

| Module | Endpoints | Description |
|---|---|---|
| Auth | `POST /login` | JWT-based authentication |
| Users | Full CRUD | User management with role-based access |
| Products | Full CRUD | Product catalog with soft delete |
| Inventory | Register + List | Stock movements (ENTRADA / SALIDA) with automatic stock update |
| Suppliers | Full CRUD | Supplier management with soft delete |
| Orders | Full CRUD | Purchase orders with price snapshots and stock decrement |
| Dashboard | `GET /summary` | Aggregated business metrics (totals, low stock, recent orders) |

---

## Architecture

The project follows a strict **layered architecture** — each layer has one responsibility and never bypasses the one below it.

```
HTTP Request
    ↓
api/v1/          → Receives HTTP, verifies JWT, serializes response
    ↓
services/        → Business logic (coordinates multiple operations)
    ↓
crud/            → Database operations only (no business logic)
    ↓
models/          → SQLAlchemy table definitions
    ↓
PostgreSQL
```

**Key design decisions:**

- `services/` layer is only introduced when an operation requires coordinating multiple database writes (inventory movements, order creation). Simple CRUD goes directly from router to `crud/`.
- `dependencies.py` centralizes session injection and authentication — endpoints never create sessions manually.
- Soft delete across all entities: records are marked `is_active=False`, never deleted.
- `created_by_id` on orders comes from the JWT, never from the request body — clients cannot forge who placed an order.
- Price in `OrderItem` is a snapshot of `unit_price` at creation time — historical orders are unaffected by future price changes.

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL (running locally or remote)

### Installation

```bash
# Clone the repository
git clone https://github.com/hermanyepes/bizcore.git
cd bizcore/backend

# Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements-dev.txt
```

### Environment setup

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/bizcore
SECRET_KEY=your_random_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
ALLOWED_ORIGINS=["http://localhost:4200"]
```

Generate a secure `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Database setup

```bash
# Create the database in PostgreSQL first, then apply all migrations
alembic upgrade head
```

### Run the server

```bash
uvicorn app.main:app --reload
```

API available at: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

---

## Running Tests

Tests use an **in-memory SQLite database** — no PostgreSQL required, no setup needed.

```bash
# Run all tests
python -m pytest -v

# Run with coverage report
python -m pytest --cov=app --cov-report=term-missing

# Run a specific test file
python -m pytest tests/integration/test_orders.py -v
```

**145 tests** covering happy paths, error cases (401, 403, 404, 409, 422), role-based access control, and security edge cases (JWT manipulation, privilege escalation attempts).

---

## API Reference

Full interactive documentation is available at `/docs` (Swagger UI) when the server is running.

### Authentication

All endpoints require a Bearer token obtained from `POST /api/v1/auth/login`.

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@bizcore.com", "password": "Admin1234"}'

# Use the token
curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <your_token>"
```

### Roles

| Role | Access |
|---|---|
| `Administrador` | Full access to all endpoints |
| `Empleado` | Read-only on most resources; can create inventory movements and orders |

### Pagination

All list endpoints support pagination:

```
GET /api/v1/products?page=1&page_size=10
```

| Parameter | Default | Constraints |
|---|---|---|
| `page` | 1 | ≥ 1 |
| `page_size` | 10 | ≥ 1, ≤ 100 |

---

## Project Structure

```
backend/
├── app/
│   ├── api/v1/          # HTTP routers (one file per module)
│   ├── core/
│   │   ├── config.py    # Environment variables (pydantic-settings)
│   │   ├── database.py  # Async engine and session factory
│   │   └── security.py  # bcrypt hashing + JWT encode/decode
│   ├── crud/            # Database operations (no business logic)
│   ├── models/          # SQLAlchemy table definitions
│   ├── schemas/         # Pydantic schemas (Create / Update / Response)
│   ├── services/        # Business logic (inventory, orders, dashboard)
│   ├── dependencies.py  # FastAPI dependency injection (get_db, auth)
│   └── main.py          # App factory and lifespan
├── alembic/             # Database migration history
├── tests/
│   ├── integration/     # HTTP-level tests (one file per module)
│   ├── unit/            # Unit tests for security utilities
│   └── conftest.py      # Shared fixtures (test DB, tokens, seed data)
├── .env.example         # Environment variable template
├── requirements.txt     # Production dependencies
├── requirements-dev.txt # Development + testing dependencies
└── pyproject.toml       # ruff and pytest configuration
```

---

## Security Notes

- Passwords are hashed with **bcrypt** directly (not passlib — [see why](https://github.com/pyca/bcrypt#compatibility))
- Login returns the same error for wrong email and wrong password — prevents user enumeration
- `password_hash` is never exposed in any response schema
- CORS origins are configured via environment variable, not hardcoded
- `is_active` check on every authenticated request — deactivated users cannot use valid tokens
