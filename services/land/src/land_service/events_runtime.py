"""Land event bus lifecycle and 48-hour reservation expiry worker."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from sqlalchemy import update

from farm_common.events import RabbitEventBus
from farm_common.outbox import run_relay
from land_service.consumers import make_handler
from land_service.database import get_session_factory
from land_service.db import OutboxEvent, Reservation, now
from land_service.settings import get_land_settings


async def expire_pending_reservations(session_factory) -> int:
    async with session_factory() as session, session.begin():
        result = await session.execute(
            update(Reservation)
            .where(Reservation.status == "PENDING", Reservation.expires_at <= now())
            .values(status="EXPIRED", updated_at=now())
        )
        return result.rowcount or 0


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
                ["payment.succeeded", "quality.graded"], make_handler(session_factory)
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
