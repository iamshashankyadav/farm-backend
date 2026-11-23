"""Land event bus lifecycle and 48-hour reservation expiry worker."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from sqlalchemy import update

from farm_common.events import Event, RabbitEventBus
from farm_common.outbox import add_event, run_relay
from land_service.consumers import make_handler
from land_service.database import get_session_factory
from land_service.db import OutboxEvent, Reservation, now
from land_service.settings import get_land_settings


async def expire_pending_reservations(session_factory) -> int:
    """Requests the farmer did not answer within 48 hours become EXPIRED; both sides are told."""
    async with session_factory() as session, session.begin():
        expired = (
            (
                await session.execute(
                    update(Reservation)
                    .where(Reservation.status == "PENDING", Reservation.expires_at <= now())
                    .values(status="EXPIRED", updated_at=now())
                    .returning(Reservation)
                )
            )
            .scalars()
            .all()
        )
        for row in expired:
            add_event(
                session,
                OutboxEvent,
                Event(
                    type="reservation.expired",
                    producer="land",
                    payload={
                        "reservationId": str(row.id),
                        "customerId": str(row.customer_id),
                        "farmerId": str(row.farmer_id),
                        "cropId": row.crop_id,
                    },
                ),
            )
        return len(expired)


async def expiry_loop(session_factory) -> None:
    while True:
        try:
            await expire_pending_reservations(session_factory)
        except Exception:
            # The next pass retries; keep the service alive if the database is briefly unavailable.
            pass
        await asyncio.sleep(60)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_land_settings()
    session_factory = get_session_factory()
    expiry = asyncio.create_task(expiry_loop(session_factory))
    bus = None
    relay = None
    try:
        if settings.events_enabled:
            bus = RabbitEventBus(settings.rabbitmq_url, service_name="land")
            await bus.connect()
            await bus.subscribe(
                ["payment.succeeded", "order.placed", "order.completed", "order.cancelled"],
                make_handler(session_factory),
            )
            relay = asyncio.create_task(run_relay(session_factory, OutboxEvent, bus))
        yield
    finally:
        expiry.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await expiry
        if relay is not None:
            relay.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay
        if bus is not None:
            await bus.close()
