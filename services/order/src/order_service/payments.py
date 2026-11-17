"""Mock payment gateway, and the bookkeeping of deposits and refunds (no real money moves)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from farm_common.events import Event
from farm_common.outbox import add_event
from order_service import events as ev
from order_service.db import HarvestRow, OrderRow, OutboxEvent, PaymentRow
from order_service.schemas import PaymentKind, PaymentStatus


class PaymentGateway(Protocol):
    async def charge(self, intent_amount: Decimal, total: Decimal) -> bool: ...


class MockPaymentGateway:
    def __init__(self, fail_amount: Decimal | None = None) -> None:
        self.fail_amount = fail_amount

    async def charge(self, intent_amount: Decimal, total: Decimal) -> bool:
        return self.fail_amount is None or intent_amount != self.fail_amount


def publish_payment_succeeded(
    session: AsyncSession,
    payment: PaymentRow,
    reference_id: UUID | None,
    order_ids: list[UUID] | None = None,
) -> None:
    add_event(
        session,
        OutboxEvent,
        Event(
            type=ev.PAYMENT_SUCCEEDED,
            producer=ev.PRODUCER,
            payload=ev.PaymentSucceededPayload(
                payment_id=payment.id,
                kind=PaymentKind(payment.kind),
                amount=float(payment.amount),
                currency=payment.currency,
                customer_id=payment.customer_id,
                reference_id=reference_id,
                order_ids=order_ids or [],
            ).model_dump(mode="json", by_alias=True),
        ),
    )


def refund_deposit(session: AsyncSession, row: HarvestRow, order_id: UUID | None) -> Decimal:
    """Record a REFUND for the deposit still held for a reservation. Returns the amount."""
    amount = row.deposit_paid - row.deposit_refunded
    if amount <= 0:
        return Decimal(0)
    row.deposit_refunded = row.deposit_paid
    session.add(
        PaymentRow(
            id=uuid4(),
            customer_id=row.customer_id,
            kind=PaymentKind.REFUND.value,
            amount=amount,
            currency="INR",
            reference_id=row.reservation_id,
            order_id=order_id,
            status=PaymentStatus.SUCCEEDED.value,
        )
    )
    return amount


async def refund_harvest_order(session: AsyncSession, order: OrderRow) -> Decimal:
    """A harvest order is cancelled: refund the deposit and close the reservation record."""
    if order.reservation_id is None:
        return Decimal(0)
    row = await session.get(HarvestRow, order.reservation_id, with_for_update=True)
    if row is None:
        return Decimal(0)
    row.status = "CANCELLED"
    row.updated_at = datetime.now(UTC)
    return refund_deposit(session, row, order.id)
