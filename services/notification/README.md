# notification service

**Owner:** Team 1

Push, email and in-app inbox, driven by events.

| | |
| --- | --- |
| Python package | `notification_service` |
| Local dev port | 8008 |
| Database schema | `notification` |

```bash
# from the repo root
uv run --package farm-notification uvicorn notification_service.main:app --reload --port 8008
# migrations (needs DATABASE_URL)
cd services/notification && uv run alembic revision --autogenerate -m "describe change"
cd services/notification && uv run alembic upgrade head
```
