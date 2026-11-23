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

## Dispatch: route offers (first to accept gets it)

When a farmer packs an order, the order service publishes `order.ready_for_dispatch`. Logistics
waits `POOL_ON_READY_DELAY_S` (5 s, so orders packed together share a pool) and runs the pooling
job for that order's delivery date. With `DISPATCH_MODE=offer` (the default) each new pool is not
assigned; it is **offered**:

1. Partners with a location ping in the last `OFFER_ONLINE_MINUTES` (30) and within
   `OFFER_RADIUS_KM` (15) of the first pickup get an offer, nearest first. Nobody that close: every
   online partner; nobody online: every known partner. `pool.offered` goes out, and the
   notification service pushes `POOL_OFFER` to each of them.
2. `POST /logistics/offers/{poolId}/accept` assigns the pool with one conditional UPDATE
   (`WHERE partner_id IS NULL`), so of two partners accepting at once exactly one wins; the other
   gets `409 POOL_TAKEN`. The winner's response is the route.
3. `pool.assigned` then goes out as before (orders become POOLED, the customer is told), and
   `pool.offer_closed` makes the notification service replace the other partners' offer
   notification with "Route taken" (same FCM `tag`).
4. `GET /logistics/offers/mine` lists a partner's open offers; `POST .../decline` turns one down.

`DISPATCH_MODE=assign` keeps the old behaviour (straight to the least-loaded partner).
