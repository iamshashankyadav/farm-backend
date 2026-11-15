# land service

**Owner:** Team 2

V2 plots, seasons, reservations, crop updates, harvest flow.

| | |
| --- | --- |
| Python package | `land_service` |
| Local dev port | 8003 |
| Database schema | `land` |

```bash
# from the repo root
uv run --package farm-land uvicorn land_service.main:app --reload --port 8003
# migrations (needs DATABASE_URL)
cd services/land && uv run alembic revision --autogenerate -m "describe change"
cd services/land && uv run alembic upgrade head
```
