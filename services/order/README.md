# order service

**Owner:** Team 1

Cart, checkout saga, V1 and V2 orders, mock payments.

| | |
| --- | --- |
| Python package | `order_service` |
| Local dev port | 8006 |
| Database schema | `order` |

```bash
# from the repo root
uv run --package farm-order uvicorn order_service.main:app --reload --port 8006
# migrations (needs DATABASE_URL)
cd services/order && uv run alembic revision --autogenerate -m "describe change"
cd services/order && uv run alembic upgrade head
```
