"""Idempotent consumers for payment and quality lifecycle events."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from farm_common.events import Event
from farm_common.outbox import mark_processed
from land_service.db import ProcessedEvent, Reservation


async def on_payment_succeeded(session: AsyncSession, event: Event) -> None:
    # The order service emits referenceId for a reservation deposit; FULL payments reference a checkout.
    if event.payload.get("kind") != "DEPOSIT":
        return
    reservation_id = event.payload.get("referenceId") or event.payload.get("reservationId")
    if not reservation_id:
        return
    row = await session.get(Reservation, UUID(str(reservation_id)), with_for_update=True)
    if row is not None and row.status == "ACCEPTED":
        row.status = "ACTIVE"
        row.deposit = event.payload.get("amount", row.deposit)


async def on_quality_graded(session: AsyncSession, event: Event) -> None:
    payload = event.payload
    if payload.get("subjectType") != "HARVEST":
        return
    reservation_id = payload.get("subjectId") or payload.get("reservationId")
    if not reservation_id:
        return
    row = await session.get(Reservation, UUID(str(reservation_id)), with_for_update=True)
    if row is None or row.status != "HARVEST_READY":
        return
    if payload.get("attempt") != row.harvest_attempt:
        return  # Ignore a delayed report from an earlier re-harvest attempt.
    if payload.get("result") == "PASS" or payload.get("resolution") == "ACCEPT_LOWER_GRADE":
        row.status = "FULFILLING"
    elif payload.get("resolution") == "REHARVEST":
        row.status = "ACTIVE"


HANDLERS: dict[str, Callable[[AsyncSession, Event], Awaitable[None]]] = {
    "payment.succeeded": on_payment_succeeded,
    "quality.graded": on_quality_graded,
}


def make_handler(session_factory: async_sessionmaker[AsyncSession]):
    async def handle(event: Event) -> None:
        handler = HANDLERS.get(event.type)
        if handler is None:
            return
        async with session_factory() as session, session.begin():
            if await mark_processed(session, ProcessedEvent, event.event_id):
                await handler(session, event)

    return handle
