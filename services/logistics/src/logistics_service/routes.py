"""Public API routes for the logistics service (HLD section 15).

Mounted at /api/v1/logistics by the gateway.

POST  /logistics/pools/run?date     Admin → trigger pooling job now
GET   /logistics/my-route?date      Delivery partner → today's assigned route
POST  /logistics/stops/{id}/pickup  Delivery partner → confirm pickup at hub
POST  /logistics/stops/{id}/deliver Delivery partner → confirm delivery + photo + OTP
POST  /logistics/location           Delivery partner → location ping (every 30 s)
GET   /logistics/orders/{id}/track  Customer → live tracking
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from farm_common.auth import CurrentUser, Role, get_current_user, require_roles
from farm_common.errors import AppError, NotFound
from logistics_service.database import get_session
from logistics_service.db import (
    DeliveryPool,
    LocationPing,
    PoolStatus,
    PoolStop,
    StopStatus,
    StopType,
)
from logistics_service.pooling import fetch_ready_orders, run_pooling
from logistics_service.schemas import (
    DeliverIn,
    LocationPingIn,
    PickupIn,
    PoolOut,
    PoolRunResponse,
    StopOut,
    TrackOut,
)
from logistics_service.settings import LogisticsSettings, get_logistics_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["logistics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stop_out(s: PoolStop) -> StopOut:
    from logistics_service.schemas import StopStatus as SStatus
    from logistics_service.schemas import StopType as SType

    return StopOut(
        id=s.id,
        pool_id=s.pool_id,
        order_id=s.order_id,
        stop_type=SType(s.stop_type),
        seq=s.seq,
        lat=s.lat,
        lng=s.lng,
        address=s.address,
        eta=s.eta,
        status=SStatus(s.status),
        photo_media_id=s.photo_media_id,
        otp_verified=s.otp_verified,
        done_at=s.done_at,
        weight_kg=s.weight_kg,
    )


async def _get_stop(session: AsyncSession, stop_id: UUID) -> PoolStop:
    stop = await session.get(PoolStop, stop_id)
    if stop is None:
        raise NotFound("Stop not found", code="STOP_NOT_FOUND")
    return stop


async def _get_pool_with_stops(
    session: AsyncSession, pool_id: UUID
) -> tuple[DeliveryPool, list[PoolStop]]:
    pool = await session.get(DeliveryPool, pool_id)
    if pool is None:
        raise NotFound("Pool not found", code="POOL_NOT_FOUND")
    result = await session.execute(
        select(PoolStop).where(PoolStop.pool_id == pool_id).order_by(PoolStop.seq)
    )
    stops = list(result.scalars())
    return pool, stops


def _pool_out(pool: DeliveryPool, stops: list[PoolStop]) -> PoolOut:
    return PoolOut(
        id=pool.id,
        pool_date=pool.pool_date,
        partner_id=pool.partner_id,
        status=PoolStatus(pool.status),
        total_km=pool.total_km,
        km_saved=pool.km_saved,
        stops=[_stop_out(s) for s in stops],
        created_at=pool.created_at,
        assigned_at=pool.assigned_at,
    )


# ---------------------------------------------------------------------------
# POST /logistics/pools/run  (Admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/pools/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PoolRunResponse,
    summary="Run the pooling job for a given date",
)
async def run_pools(
    pool_date: date = Query(default_factory=date.today, description="Date to pool orders for"),
    _user: CurrentUser = Depends(require_roles(Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
    settings: LogisticsSettings = Depends(get_logistics_settings),
) -> PoolRunResponse:
    """Fetch READY_FOR_DISPATCH orders, cluster them, persist pools, publish pool.assigned."""
    from logistics_service.database import get_session_factory

    orders = await fetch_ready_orders(pool_date, settings.order_service_url)
    pools = await run_pooling(pool_date, orders, get_session_factory(), settings)

    # Reload with stops for the response
    pool_outs: list[PoolOut] = []
    for p in pools:
        _, stops = await _get_pool_with_stops(session, p.id)
        pool_outs.append(_pool_out(p, stops))

    return PoolRunResponse(pools_created=len(pools), pools=pool_outs)


# ---------------------------------------------------------------------------
# GET /logistics/my-route  (Delivery partner)
# ---------------------------------------------------------------------------


@router.get(
    "/my-route",
    response_model=PoolOut,
    summary="Today's assigned pool for the authenticated delivery partner",
)
async def my_route(
    pool_date: date = Query(default_factory=date.today),
    user: CurrentUser = Depends(require_roles(Role.DELIVERY)),
    session: AsyncSession = Depends(get_session),
) -> PoolOut:
    result = await session.execute(
        select(DeliveryPool)
        .where(
            DeliveryPool.partner_id == UUID(user.id),
            DeliveryPool.pool_date == pool_date,
        )
        .order_by(DeliveryPool.created_at.desc())
        .limit(1)
    )
    pool = result.scalar_one_or_none()
    if pool is None:
        raise NotFound("No pool assigned for this date", code="NO_POOL")
    _, stops = await _get_pool_with_stops(session, pool.id)
    return _pool_out(pool, stops)


# ---------------------------------------------------------------------------
# POST /logistics/stops/{id}/pickup  (Delivery partner)
# ---------------------------------------------------------------------------


@router.post(
    "/stops/{stop_id}/pickup",
    response_model=StopOut,
    summary="Mark a PICKUP stop as done",
)
async def confirm_pickup(
    stop_id: UUID,
    body: PickupIn,
    user: CurrentUser = Depends(require_roles(Role.DELIVERY)),
    session: AsyncSession = Depends(get_session),
) -> StopOut:
    async with session.begin():
        stop = await _get_stop(session, stop_id)
        if stop.stop_type != StopType.PICKUP:
            raise AppError("WRONG_STOP_TYPE", "This stop is not a PICKUP stop", 422)
        if stop.status == StopStatus.DONE:
            return _stop_out(stop)
        stop.status = StopStatus.DONE
        stop.done_at = datetime.now(UTC)
        if body.weight_kg is not None:
            stop.weight_kg = body.weight_kg
    return _stop_out(stop)


# ---------------------------------------------------------------------------
# POST /logistics/stops/{id}/deliver  (Delivery partner)
# ---------------------------------------------------------------------------

# Simple 4-digit OTP: in production this would be verified against an OTP
# issued to the customer; for the scaffold we accept any 4-digit value and
# set otp_verified = True (the real check lives in the order service).


@router.post(
    "/stops/{stop_id}/deliver",
    response_model=StopOut,
    summary="Complete a DROP stop with photo proof + OTP",
)
async def confirm_delivery(
    stop_id: UUID,
    body: DeliverIn,
    user: CurrentUser = Depends(require_roles(Role.DELIVERY)),
    session: AsyncSession = Depends(get_session),
) -> StopOut:
    async with session.begin():
        stop = await _get_stop(session, stop_id)
        if stop.stop_type != StopType.DROP:
            raise AppError("WRONG_STOP_TYPE", "This stop is not a DROP stop", 422)
        if stop.status == StopStatus.DONE:
            return _stop_out(stop)
        if not body.otp.isdigit():
            raise AppError("INVALID_OTP", "OTP must be 4 digits", 422)
        stop.photo_media_id = body.photo_media_id
        stop.otp_verified = True
        stop.status = StopStatus.DONE
        stop.done_at = datetime.now(UTC)
    return _stop_out(stop)


# ---------------------------------------------------------------------------
# POST /logistics/location  (Delivery partner)
# ---------------------------------------------------------------------------


@router.post(
    "/location",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record a GPS location ping (every 30 s while on route)",
)
async def record_location(
    body: LocationPingIn,
    user: CurrentUser = Depends(require_roles(Role.DELIVERY)),
    session: AsyncSession = Depends(get_session),
) -> None:
    async with session.begin():
        session.add(
            LocationPing(
                partner_id=UUID(user.id),
                pool_id=body.pool_id,
                lat=body.lat,
                lng=body.lng,
                accuracy_m=body.accuracy_m,
                speed_ms=body.speed_ms,
                heading=body.heading,
                recorded_at=datetime.now(UTC),
            )
        )


# ---------------------------------------------------------------------------
# GET /logistics/orders/{id}/track  (Customer)
# ---------------------------------------------------------------------------


@router.get(
    "/orders/{order_id}/track",
    response_model=TrackOut,
    summary="Live tracking for a customer order",
)
async def track_order(
    order_id: UUID,
    _user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TrackOut:
    # Find the active DROP stop for this order
    result = await session.execute(
        select(PoolStop)
        .where(
            PoolStop.order_id == order_id,
            PoolStop.stop_type == StopType.DROP,
        )
        .order_by(PoolStop.seq.desc())
        .limit(1)
    )
    stop = result.scalar_one_or_none()

    partner_lat = partner_lng = None
    partner_updated_at = None
    pool_id = stop.pool_id if stop else None

    if pool_id:
        # Latest ping from the partner assigned to this pool
        pool = await session.get(DeliveryPool, pool_id)
        if pool and pool.partner_id:
            ping_result = await session.execute(
                select(LocationPing)
                .where(LocationPing.partner_id == pool.partner_id)
                .order_by(LocationPing.recorded_at.desc())
                .limit(1)
            )
            ping = ping_result.scalar_one_or_none()
            if ping:
                partner_lat = ping.lat
                partner_lng = ping.lng
                partner_updated_at = ping.recorded_at

    return TrackOut(
        order_id=order_id,
        pool_id=pool_id,
        stop=_stop_out(stop) if stop else None,
        partner_lat=partner_lat,
        partner_lng=partner_lng,
        partner_updated_at=partner_updated_at,
    )
