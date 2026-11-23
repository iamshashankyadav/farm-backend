# land service

**Owner:** Team 2

V2 plots, seasons, reservations, crop updates and harvest lifecycle.

| | |
| --- | --- |
| Python package | `land_service` |
| Local dev port | 8003 |
| Database schema | `land` |

## API

The gateway exposes the service at `/api/v1/land`.

- `POST /plots`, `GET /plots/mine`, `GET /plots/{plotId}`, `PATCH /plots/{plotId}`, `DELETE /plots/{plotId}`
- `POST /plots/{plotId}/seasons`, `GET /plots/{plotId}/seasons`, `PATCH|DELETE /plots/{plotId}/seasons/{seasonId}`
- `GET /plots/search` accepts either `lat,lng,radius_km` or `west,south,east,north`, plus optional `season` and `crop`
- `POST /reservations`, `GET /reservations/mine`, `POST /reservations/{id}/accept|reject|cancel`
- `POST /reservations/{id}/updates` and `POST /reservations/{id}/harvest-ready`

Plot boundaries are GeoJSON Polygon coordinates in `[longitude, latitude]` order (SRID 4326). The service validates the ring, checks PostGIS validity and overlap, and calculates area in acres using geography. Plot photos are owned by media as `ownerType=PLOT`; the private `/internal/geo/plot/{id}` route lets the media worker verify EXIF GPS.

Reservations have a database partial unique index for PENDING, ACCEPTED, ACTIVE and HARVEST_READY, and PENDING requests expire after 48 hours. Deposit payment success activates the reservation. The provisional deposit rate defaults to 20% of the season total and is configurable with `LAND_DEPOSIT_RATE` (0–1); confirm the final policy with the team. Seasons of one plot never overlap (409 `SEASON_OVERLAP`, backed by an exclusion constraint that needs the `btree_gist` extension). A request left unanswered for 48 hours becomes EXPIRED (a worker sweeps every minute, and a new request on the season expires stale ones at once); search hides ended and taken seasons, and a farmer cannot reserve their own plot. Only admin-verified farmers may list plots. `harvest-ready` takes the harvested weight (`harvestedQtyKg`); there is no quality gate, so the order service makes the harvest order at once. The reservation follows its harvest order: `order.placed` → FULFILLING (the customer chooses delivery or buy-back), `order.completed` → COMPLETED, `order.cancelled` → CANCELLED. Land publishes `reservation.requested`, `rejected`, `cancelled` (with `cancelledBy`), `expired`, `activated` and `crop.updated` so both sides are told.

## Migrations and local run

```bash
# from the repo root
uv run --package farm-land uvicorn land_service.main:app --reload --port 8003
cd services/land && uv run alembic upgrade head
```

The database must have PostGIS enabled. Set `EVENTS_ENABLED=false` for isolated local API work without RabbitMQ.
