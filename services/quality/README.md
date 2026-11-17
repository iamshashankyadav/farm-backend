# quality service

**Owner:** Team 2

Inspections and grades for produce batches and harvests.

| | |
| --- | --- |
| Python package | `quality_service` |
| Local dev port | 8005 |
| Database schema | `quality` |

## API

The gateway exposes the service at `/api/v1/quality`.

- `PUT /inspectors/me/location` registers an inspector's GeoJSON location and availability
- `GET /inspections` lists assigned and unassigned inspections
- `POST /inspections/{id}/claim` claims an unassigned inspection
- `POST /inspections/{id}/report` records grade A/B/C, moisture, pest presence, estimated weight, photos and the result

The service consumes `order.packed` and `harvest.ready`. It creates one inspection per order or per harvest attempt and assigns the nearest available inspector using PostGIS KNN (`<->`) when a source location is included; an unassigned inspection can be claimed by an inspector. Reports are written with a transactional outbox and publish `quality.graded`. For HARVEST, a failure requires either REHARVEST or ACCEPT_LOWER_GRADE.

## Migrations and local run

```bash
# from the repo root
uv run --package farm-quality uvicorn quality_service.main:app --reload --port 8005
cd services/quality && uv run alembic upgrade head
```

The database must have PostGIS enabled. Set `EVENTS_ENABLED=false` for isolated local API work without RabbitMQ.
