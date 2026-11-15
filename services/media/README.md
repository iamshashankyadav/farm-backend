# media service

**Owner:** Team 2

Signed photo uploads, EXIF/GPS verification, thumbnails.

| | |
| --- | --- |
| Python package | `media_service` |
| Local dev port | 8004 |
| Database schema | `media` |

```bash
# from the repo root
uv run --package farm-media uvicorn media_service.main:app --reload --port 8004
# migrations (needs DATABASE_URL)
cd services/media && uv run alembic revision --autogenerate -m "describe change"
cd services/media && uv run alembic upgrade head
```
