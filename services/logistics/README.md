# logistics service

**Owner:** Team 1 · Slot M2 · Sprint 3 (Issue #19)

Delivery pooling, routes, partner app API, tracking, and proof of delivery.

| | |
| --- | --- |
| Python package | `logistics_service` |
| Local dev port | 8007 |
| Database schema | `logistics` |
| Route prefix | `/api/v1/logistics` |

---

## Features & Architecture

### 1. Delivery Pooling Job (`POST /pools/run` & Nightly Cron)
- **Clustering**: Groups orders ready for dispatch using **DBSCAN** (`eps ≈ 3.0 km`, haversine metric) on delivery drop coordinates.
- **Capacity Splitting**: Divides oversized clusters into sub-clusters when total weight exceeds partner capacity (`partner_capacity_kg = 50.0 kg`).
- **Pickup-Before-Drop Constraint**: Sequenced so hub pickup stops precede customer drop stops.
- **OSRM Routing Integration**: Calls the OSRM Trip API to obtain the optimal waypoint ordering, polyline geometry, per-stop ETAs, `total_km`, and `km_saved` versus separate individual trips.
- **Event Publishing**: Publishes `pool.assigned` with pool metadata and stops via the transactional outbox (`farm_common.outbox`).

### 2. Worker & Nightly Cron
- An **arq** worker (`logistics_service.worker.WorkerSettings`) executes the nightly pooling cron job at `20:30 UTC` (`02:00 IST`).
- Can also be triggered on-demand via `POST /api/v1/logistics/pools/run?date=YYYY-MM-DD`.

---

## Local Development & Testing

```bash
# Start API locally
uv run --package farm-logistics uvicorn logistics_service.main:app --reload --port 8007

# Run worker locally
uv run --package farm-logistics arq logistics_service.worker.WorkerSettings

# Run migrations (requires DATABASE_URL)
cd services/logistics && uv run alembic upgrade head

# Run tests
uv run pytest services/logistics
```
