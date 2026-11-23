"""Idempotent consumers for payment and harvest-order lifecycle events.

payment.succeeded (kind DEPOSIT)       ACCEPTED -> ACTIVE; the farmer is told to start growing
order.placed (HARVEST order)           HARVEST_READY -> FULFILLING: the harvest order exists and the
                                       customer picks delivery or buy-back
order.completed (HARVEST order)        -> COMPLETED: delivered, or bought back
order.cancelled (HARVEST order)        -> CANCELLED: the customer cancelled the harvest order (the
                                       order service refunds the deposit)
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from farm_common.events import Event
from farm_common.outbox import add_event, mark_processed
from land_service.db import OutboxEvent, ProcessedEvent, Reservation


def _reservation_id(payload: dict) -> UUID | None:
    value = payload.get("reservationId") or payload.get("referenceId")
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


async def on_payment_succeeded(session: AsyncSession, event: Event) -> None:
    # The order service emits referenceId for a reservation deposit; FULL payments reference a checkout.
    if event.payload.get("kind") != "DEPOSIT":
        return
    reservation_id = _reservation_id(event.payload)
    if reservation_id is None:
        return
    row = await session.get(Reservation, reservation_id, with_for_update=True)
    if row is not None and row.status == "ACCEPTED":
        row.status = "ACTIVE"
        row.deposit = event.payload.get("amount", row.deposit)
        add_event(
            session,
            OutboxEvent,
            Event(
                type="reservation.activated",
                producer="land",
                payload={
                    "reservationId": str(row.id),
                    "customerId": str(row.customer_id),
                    "farmerId": str(row.farmer_id),
                    "cropId": row.crop_id,
                    "deposit": float(row.deposit) if row.deposit is not None else None,
                },
            ),
        )


# harvest-order event -> (statuses it may move from, status it moves to)
HARVEST_ORDER_STEPS: dict[str, tuple[tuple[str, ...], str]] = {
    "order.placed": (("HARVEST_READY",), "FULFILLING"),
    "order.completed": (("HARVEST_READY", "FULFILLING"), "COMPLETED"),
    "order.cancelled": (("HARVEST_READY", "FULFILLING"), "CANCELLED"),
}


async def on_harvest_order(session: AsyncSession, event: Event) -> None:
    if event.payload.get("orderType") != "HARVEST":
        return  # produce orders do not concern land
    reservation_id = _reservation_id(event.payload)
    if reservation_id is None:
        return
    allowed, target = HARVEST_ORDER_STEPS[event.type]
    row = await session.get(Reservation, reservation_id, with_for_update=True)
    if row is not None and row.status in allowed:
        row.status = target


HANDLERS: dict[str, Callable[[AsyncSession, Event], Awaitable[None]]] = {
    "payment.succeeded": on_payment_succeeded,
    "order.placed": on_harvest_order,
    "order.completed": on_harvest_order,
    "order.cancelled": on_harvest_order,
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
