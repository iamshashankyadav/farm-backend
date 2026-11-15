# logistics service

**Owner:** Team 1

Delivery pooling, routes, partner app API, tracking, proof of delivery.

| | |
| --- | --- |
| Python package | `logistics_service` |
| Local dev port | 8007 |
| Database schema | `logistics` |

```bash
# from the repo root
uv run --package farm-logistics uvicorn logistics_service.main:app --reload --port 8007
# migrations (needs DATABASE_URL)
cd services/logistics && uv run alembic revision --autogenerate -m "describe change"
cd services/logistics && uv run alembic upgrade head
```
