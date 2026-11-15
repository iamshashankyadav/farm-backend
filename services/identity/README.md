# identity service

**Owner:** Joint

Users, roles, phone OTP, JWT issue and refresh, farmer verification.

| | |
| --- | --- |
| Python package | `identity_service` |
| Local dev port | 8001 |
| Database schema | `identity` |

```bash
# from the repo root
uv run --package farm-identity uvicorn identity_service.main:app --reload --port 8001
# migrations (needs DATABASE_URL)
cd services/identity && uv run alembic revision --autogenerate -m "describe change"
cd services/identity && uv run alembic upgrade head
```
