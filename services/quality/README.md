# quality service

**Owner:** Team 2

Inspections and grades for produce batches and harvests.

| | |
| --- | --- |
| Python package | `quality_service` |
| Local dev port | 8005 |
| Database schema | `quality` |

```bash
# from the repo root
uv run --package farm-quality uvicorn quality_service.main:app --reload --port 8005
# migrations (needs DATABASE_URL)
cd services/quality && uv run alembic revision --autogenerate -m "describe change"
cd services/quality && uv run alembic upgrade head
```
