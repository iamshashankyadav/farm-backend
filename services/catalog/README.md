# catalog service

**Owner:** Team 2

V1 farms and produce listings, geo search, stock reserve/release.

| | |
| --- | --- |
| Python package | `catalog_service` |
| Local dev port | 8002 |
| Database schema | `catalog` |

```bash
# from the repo root
uv run --package farm-catalog uvicorn catalog_service.main:app --reload --port 8002
# migrations (needs DATABASE_URL)
cd services/catalog && uv run alembic revision --autogenerate -m "describe change"
cd services/catalog && uv run alembic upgrade head
```
