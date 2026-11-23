"""Dispatch: offer a new pool to nearby delivery partners; the first to accept gets it.

Flow (dispatch_mode = "offer"):
1. The pooling job saves a pool without a partner (status PENDING).
2. `offer_pool` picks partners: online (a location ping in the last `offer_online_minutes`) and
   within `offer_radius_km` of the first pickup, nearest first. With nobody that close it widens
   to every online partner, then to every known partner. One `pool_offers` row per partner, and a
   `pool.offered` event (outbox) that the notification service pushes to each of them.
3. `accept_offer` assigns the pool with one conditional UPDATE
   (`... WHERE id = :pool AND partner_id IS NULL`). Postgres row locking makes that race-free:
   of two partners accepting at once exactly one row update succeeds, the other gets
   409 POOL_TAKEN. The winner's offer becomes ACCEPTED, everyone else's TAKEN, and two events go
   out: `pool.assigned` (the order service marks the orders POOLED, the customer is told) and
   `pool.offer_closed` (the other partners' offer notifications are replaced).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from farm_common.errors import AppError, NotFound
from farm_common.events import Event
from farm_common.outbox import add_event
from logistics_service.db import (
    DeliveryPartner,
    DeliveryPool,
    LocationPing,
    OfferStatus,
    OutboxEvent,
    PoolOffer,
    PoolStatus,
    PoolStop,
    StopType,
)
from logistics_service.sequencing import haversine_km
from logistics_service.settings import LogisticsSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Candidate:
    partner_id: UUID
    # Where the partner is (latest ping) or lives; None when unknown
    position: tuple[float, float] | None
    online: bool


def pick_offer_targets(
    candidates: list[Candidate], first_pickup: tuple[float, float], radius_km: float
) -> list[tuple[UUID, float | None]]:
    """Who is offered the pool, nearest first, with the distance to the first pickup.

    Online partners within the radius; if none, every online partner; if nobody is online,
    every known partner (so a pool is never offered to no one while partners exist).
    """

    def dist(c: Candidate) -> float | None:
        return haversine_km(c.position, first_pickup) if c.position else None

    def by_distance(cs: list[Candidate]) -> list[tuple[UUID, float | None]]:
        rows = [(c.partner_id, dist(c)) for c in cs]
        return sorted(rows, key=lambda r: (r[1] is None, r[1] or 0.0))

    online = [c for c in candidates if c.online]
    near = [c for c in online if (d := dist(c)) is not None and d <= radius_km]
    if near:
        return by_distance(near)
    if online:
        return by_distance(online)
    return by_distance(candidates)


async def _candidates(session: AsyncSession, online_since: datetime) -> list[Candidate]:
    partners = (await session.execute(select(DeliveryPartner))).scalars().all()
    if not partners:
        return []
    # Latest ping per partner
    latest = (
        select(LocationPing.partner_id, func.max(LocationPing.recorded_at).label("at"))
        .group_by(LocationPing.partner_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                LocationPing.partner_id,
                LocationPing.lat,
                LocationPing.lng,
                LocationPing.recorded_at,
            ).join(
                latest,
                (LocationPing.partner_id == latest.c.partner_id)
                & (LocationPing.recorded_at == latest.c.at),
            )
        )
    ).all()
    last = {pid: ((lat, lng), at) for pid, lat, lng, at in rows}
    out: list[Candidate] = []
    for p in partners:
        ping = last.get(p.id)
        home = (
            (p.home_lat, p.home_lng) if p.home_lat is not None and p.home_lng is not None else None
        )
        position = ping[0] if ping else home
        online = bool(ping and ping[1] >= online_since)
        out.append(Candidate(p.id, position, online))
    return out


def _offer_payload(
    pool: DeliveryPool, stops: list[PoolStop], expires_at: datetime
) -> dict[str, Any]:
    pickups = [s for s in stops if s.stop_type == StopType.PICKUP]
    first = min(pickups, key=lambda s: s.seq) if pickups else None
    return {
        "poolId": str(pool.id),
        "poolDate": pool.pool_date.isoformat(),
        "stopCount": len(stops),
        "pickupCount": len(pickups),
        "dropCount": len(stops) - len(pickups),
        "totalKm": pool.total_km,
        "firstPickup": {"lat": first.lat, "lng": first.lng, "address": first.address}
        if first
        else None,
        "expiresAt": expires_at.isoformat(),
    }


async def offer_pool(
    session: AsyncSession, pool: DeliveryPool, stops: list[PoolStop], settings: LogisticsSettings
) -> list[UUID]:
    """Create one offer per chosen partner and publish `pool.offered`. Returns the partner ids."""
    pickups = [s for s in stops if s.stop_type == StopType.PICKUP]
    if not pickups:
        return []
    first = min(pickups, key=lambda s: s.seq)
    now = datetime.now(UTC)
    targets = pick_offer_targets(
        await _candidates(session, now - timedelta(minutes=settings.offer_online_minutes)),
        (first.lat, first.lng),
        settings.offer_radius_km,
    )
    if not targets:
        logger.info("Pool %s: no delivery partners to offer it to", pool.id)
        return []
    expires_at = now + timedelta(seconds=settings.offer_ttl_s)
    for partner_id, km in targets:
        session.add(
            PoolOffer(
                pool_id=pool.id,
                partner_id=partner_id,
                status=OfferStatus.OFFERED,
                distance_km=round(km, 2) if km is not None else None,
                expires_at=expires_at,
            )
        )
    payload = _offer_payload(pool, stops, expires_at)
    payload["offers"] = [
        {"partnerId": str(pid), "distanceKm": round(km, 2) if km is not None else None}
        for pid, km in targets
    ]
    add_event(
        session, OutboxEvent, Event(type="pool.offered", producer="logistics", payload=payload)
    )
    logger.info("Pool %s offered to %d partner(s)", pool.id, len(targets))
    return [pid for pid, _ in targets]


async def accept_offer(session: AsyncSession, pool_id: UUID, partner_id: UUID) -> DeliveryPool:
    """Assign the pool to `partner_id` if nobody has it yet. Call inside a transaction."""
    offer = (
        await session.execute(
            select(PoolOffer).where(
                PoolOffer.pool_id == pool_id, PoolOffer.partner_id == partner_id
            )
        )
    ).scalar_one_or_none()
    if offer is None:
        raise NotFound("No offer of this pool for you", code="OFFER_NOT_FOUND")

    # The race is decided here: only one UPDATE can see partner_id IS NULL.
    won = (
        await session.execute(
            update(DeliveryPool)
            .where(DeliveryPool.id == pool_id, DeliveryPool.partner_id.is_(None))
            .values(
                partner_id=partner_id, status=PoolStatus.ASSIGNED, assigned_at=datetime.now(UTC)
            )
            .returning(DeliveryPool.id)
        )
    ).scalar_one_or_none()
    if won is None:
        pool = await session.get(DeliveryPool, pool_id)
        if pool is not None and pool.partner_id == partner_id:
            return pool  # accepted twice (double tap / retry): still yours
        offer.status = OfferStatus.TAKEN
        raise AppError("POOL_TAKEN", "Another delivery partner accepted this route first", 409)

    now = datetime.now(UTC)
    offers = (
        (await session.execute(select(PoolOffer).where(PoolOffer.pool_id == pool_id)))
        .scalars()
        .all()
    )
    others: list[str] = []
    for o in offers:
        if o.partner_id == partner_id:
            o.status, o.responded_at = OfferStatus.ACCEPTED, now
        elif o.status == OfferStatus.OFFERED:
            o.status = OfferStatus.TAKEN
            others.append(str(o.partner_id))

    pool = await session.get(DeliveryPool, pool_id, populate_existing=True)
    assert pool is not None
    stops = list(
        (
            await session.execute(
                select(PoolStop).where(PoolStop.pool_id == pool_id).order_by(PoolStop.seq)
            )
        ).scalars()
    )
    from logistics_service.pooling import _pool_payload  # local import: pooling imports this module

    add_event(
        session,
        OutboxEvent,
        Event(type="pool.assigned", producer="logistics", payload=_pool_payload(pool, stops)),
    )
    if others:
        add_event(
            session,
            OutboxEvent,
            Event(
                type="pool.offer_closed",
                producer="logistics",
                payload={
                    "poolId": str(pool_id),
                    "poolDate": pool.pool_date.isoformat(),
                    "partnerIds": others,
                },
            ),
        )
    return pool


async def decline_offer(session: AsyncSession, pool_id: UUID, partner_id: UUID) -> None:
    offer = (
        await session.execute(
            select(PoolOffer).where(
                PoolOffer.pool_id == pool_id, PoolOffer.partner_id == partner_id
            )
        )
    ).scalar_one_or_none()
    if offer is None:
        raise NotFound("No offer of this pool for you", code="OFFER_NOT_FOUND")
    if offer.status == OfferStatus.OFFERED:
        offer.status, offer.responded_at = OfferStatus.DECLINED, datetime.now(UTC)


async def open_offers(
    session: AsyncSession, partner_id: UUID
) -> list[tuple[PoolOffer, DeliveryPool, list[PoolStop]]]:
    """This partner's offers whose pool nobody has taken yet, newest first."""
    rows = (
        await session.execute(
            select(PoolOffer, DeliveryPool)
            .join(DeliveryPool, DeliveryPool.id == PoolOffer.pool_id)
            .where(
                PoolOffer.partner_id == partner_id,
                PoolOffer.status == OfferStatus.OFFERED,
                DeliveryPool.partner_id.is_(None),
            )
            .order_by(PoolOffer.created_at.desc())
        )
    ).all()
    out = []
    for offer, pool in rows:
        stops = list(
            (
                await session.execute(
                    select(PoolStop).where(PoolStop.pool_id == pool.id).order_by(PoolStop.seq)
                )
            ).scalars()
        )
        out.append((offer, pool, stops))
    return out
