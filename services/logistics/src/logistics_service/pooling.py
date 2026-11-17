"""Core pooling engine: DBSCAN → OSRM → persist pools → publish pool.assigned.

Entry point: `run_pooling(pool_date, session_factory, settings)`.

Steps:
1. Fetch all orders ready for dispatch on `pool_date` (via internal order API
   or a denormalised copy in the logistics schema; for testability the caller
   passes a list of order dicts directly in the worker ctx).
2. Run DBSCAN clustering (eps ≈ 3 km, capacity-aware splitting).
3. For each cluster:
   a. Build waypoint list: hub first, then all pickups, then all drops
      (pickup-before-drop constraint).
   b. Call OSRM Trip API for optimised route + ETAs.
   c. Persist DeliveryPool + PoolStop rows.
   d. Publish `pool.assigned` via the outbox (same transaction).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from farm_common.events import Event
from farm_common.outbox import add_event
from logistics_service.clustering import cluster_orders
from logistics_service.db import (
    DeliveryPool,
    OutboxEvent,
    PoolStatus,
    PoolStop,
    StopStatus,
    StopType,
)
from logistics_service.routing import RouteResult, get_route
from logistics_service.settings import LogisticsSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Order = dict[str, Any]  # order dict produced by the caller / order service


def _wkt_point(lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def _wkt_linestring(coords: list[tuple[float, float]]) -> WKTElement | None:
    if len(coords) < 2:
        return None
    pairs = " ".join(f"{lng} {lat}" for lat, lng in coords)
    return WKTElement(f"LINESTRING({pairs})", srid=4326)


def _pool_payload(pool: DeliveryPool, stops: list[PoolStop]) -> dict[str, Any]:
    return {
        "poolId": str(pool.id),
        "poolDate": pool.pool_date.isoformat(),
        "partnerId": str(pool.partner_id) if pool.partner_id else None,
        "totalKm": pool.total_km,
        "kmSaved": pool.km_saved,
        "stopCount": len(stops),
        "orderIds": list({str(s.order_id) for s in stops}),
    }


# ---------------------------------------------------------------------------
# Single-pool persistence
# ---------------------------------------------------------------------------


async def _persist_pool(
    session: AsyncSession,
    pool_date: date,
    cluster: list[Order],
    route: RouteResult | None,
    depart: datetime,
) -> tuple[DeliveryPool, list[PoolStop]]:
    """Write one DeliveryPool + its PoolStop rows, publish pool.assigned.

    Pickup-before-drop ordering: all PICKUP stops get seq 1..k, all DROP
    stops get seq k+1..n; within each group we keep cluster order (which
    follows OSRM's waypoint_order when route is available).
    """
    pool_id = uuid4()

    # Build the route geometry
    geom = _wkt_linestring(route.linestring_coords) if route else None
    total_km = route.total_km if route else None
    km_saved = route.km_saved if route else None
    osrm_meta = route.osrm_meta if route else None

    pool = DeliveryPool(
        id=pool_id,
        pool_date=pool_date,
        partner_id=None,  # assigned later by dispatch
        status=PoolStatus.PENDING,
        geom=geom,  # type: ignore[arg-type]
        total_km=total_km,
        km_saved=km_saved,
        osrm_meta=osrm_meta,
    )
    session.add(pool)

    # Reorder cluster by OSRM waypoint_order if available (skip index 0 = hub)
    ordered = cluster
    if route and route.waypoint_order:
        # waypoint_order contains original indices into [hub, *stops]
        # index 0 is hub; drop it and map back to cluster
        stop_order = [i - 1 for i in route.waypoint_order if i > 0]
        if len(stop_order) == len(cluster):
            ordered = [cluster[i] for i in stop_order]

    # ETA lookup: route.etas are aligned to route.waypoint_order (stops only)
    etas: list[datetime | None] = []
    if route and route.etas:
        eta_map: dict[int, datetime] = {}
        stop_indices = [i - 1 for i in route.waypoint_order if i > 0]
        for pos, orig_idx in enumerate(stop_indices):
            if pos < len(route.etas):
                eta_map[orig_idx] = route.etas[pos]
        etas = [eta_map.get(i) for i in range(len(cluster))]
    else:
        etas = [None] * len(cluster)

    stops: list[PoolStop] = []
    seq = 1

    def _make_stop(order: Order, stype: StopType, s: int, eta: datetime | None) -> PoolStop:
        lat = order["drop_lat"] if stype == StopType.DROP else order["hub_lat"]
        lng = order["drop_lng"] if stype == StopType.DROP else order["hub_lng"]
        return PoolStop(
            id=uuid4(),
            pool_id=pool_id,
            order_id=UUID(str(order["order_id"])),
            stop_type=stype.value,
            seq=s,
            lat=lat,
            lng=lng,
            geom=_wkt_point(lat, lng),  # type: ignore[arg-type]
            address=order.get("address"),
            eta=eta,
            status=StopStatus.PENDING,
            weight_kg=order.get("weight_kg"),
        )

    # We model each order as 2 stops: PICKUP at hub, DROP at customer
    for i, order in enumerate(ordered):
        eta = etas[i] if i < len(etas) else None
        pickup = _make_stop(order, StopType.PICKUP, seq, eta)
        session.add(pickup)
        stops.append(pickup)
        seq += 1

    for i, order in enumerate(ordered):
        eta = etas[i] if i < len(etas) else None
        drop = _make_stop(order, StopType.DROP, seq, eta)
        session.add(drop)
        stops.append(drop)
        seq += 1

    # Publish pool.assigned (transactional outbox)
    add_event(
        session,
        OutboxEvent,
        Event(
            type="pool.assigned",
            producer="logistics",
            payload=_pool_payload(pool, stops),
        ),
    )
    return pool, stops


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pooling(
    pool_date: date,
    orders: list[Order],
    session_factory: async_sessionmaker[AsyncSession],
    settings: LogisticsSettings,
) -> list[DeliveryPool]:
    """Run the full pooling job for `pool_date`.

    `orders` is a list of dicts with keys:
        order_id, hub_lat, hub_lng, drop_lat, drop_lng,
        weight_kg (float), address (str | None)

    Returns the created DeliveryPool objects.
    """
    if not orders:
        logger.info("No orders to pool on %s", pool_date)
        return []

    pools_list = cluster_orders(
        orders,
        eps_km=settings.dbscan_eps_km,
        capacity_kg=settings.partner_capacity_kg,
    )
    logger.info("Clustered %d orders into %d pools on %s", len(orders), len(pools_list), pool_date)

    depart = datetime.now(UTC).replace(hour=6, minute=0, second=0, microsecond=0)
    created: list[DeliveryPool] = []

    for cluster in pools_list:
        # Waypoints: hub first (use hub of first order), then drop locations
        hub_lat = cluster[0]["hub_lat"]
        hub_lng = cluster[0]["hub_lng"]
        waypoints = [(hub_lat, hub_lng)] + [(o["drop_lat"], o["drop_lng"]) for o in cluster]

        route = await get_route(
            waypoints,
            depart_at=depart,
            osrm_base_url=settings.osrm_base_url,
        )

        async with session_factory() as session, session.begin():
            pool, _stops = await _persist_pool(session, pool_date, cluster, route, depart)
        created.append(pool)

    logger.info("Created %d pools for %s", len(created), pool_date)
    return created


# ---------------------------------------------------------------------------
# Fetch pending orders (called from routes when no external data is passed)
# ---------------------------------------------------------------------------


async def fetch_ready_orders(
    pool_date: date,
    order_service_url: str,
) -> list[Order]:
    """Fetch orders in READY_FOR_DISPATCH status from the order service.

    Returns an empty list when the service is unavailable – the pooling job
    will then create zero pools (safe, can be re-run on demand).
    """
    import httpx

    url = f"{order_service_url}/internal/orders/ready-for-dispatch"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"date": pool_date.isoformat()})
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Could not fetch orders from %s: %s", url, exc)
        return []
