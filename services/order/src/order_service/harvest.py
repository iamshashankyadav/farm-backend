"""V2 harvest orders (issue #24): deposits, the harvest order, DELIVERY or BUYBACK, balance, refunds.

How a reservation becomes money and an order (HLD section 12):

    reservation.accepted   we remember the reservation: customer, farmer and the deposit
    POST /orders/payments/intent {kind: DEPOSIT, referenceId: <reservation id>}
                           the deposit is taken; `payment.succeeded` (kind DEPOSIT) tells land to
                           activate the reservation
    harvest.ready          we remember the crop and where it is (the pickup point of the harvest)
    quality.graded (HARVEST)
        PASS                  -> a HARVEST order is created (status PLACED, no option yet)
        FAIL + ACCEPT_LOWER_GRADE -> the same, at the lower-grade price
        FAIL + REHARVEST / undecided -> no order; the farmer harvests again
    POST /orders/harvest   the customer picks DELIVERY or BUYBACK
        DELIVERY -> the order goes to READY_FOR_DISPATCH (logistics pools it like any order);
                    when `delivery.completed` arrives the balance (total - deposit) is charged and
                    the order is COMPLETED (a deposit above the total is refunded instead)
        BUYBACK  -> the farmer buys the harvest: the customer is credited (a REFUND payment) and
                    the order is COMPLETED right away

Harvest orders skip the packing and quality steps of a produce order (the harvest was graded before
the order existed), so `order.packed` is never published for them: quality would open a second
inspection. Every assumption made here is listed in docs/m1-assumptions.md under "Added by #24".
"""

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from farm_common.auth import CurrentUser
from farm_common.errors import AppError, Conflict, NotFound
from order_service import events as ev
from order_service.db import (
    CheckoutRow,
    HarvestRow,
    OrderEventRow,
    OrderItemRow,
    OrderRow,
    PaymentRow,
)
from order_service.payments import PaymentGateway, publish_payment_succeeded, refund_deposit
from order_service.schemas import (
    HarvestOption,
    HarvestOrderChoice,
    OrderDetail,
    OrderStatus,
    PaymentIntent,
    PaymentKind,
    PaymentStatus,
)
from order_service.service import (
    _LOAD,
    _delivery_date,
    _detail,
    _intent_schema,
    _load_order,
    _money,
    _now,
    _pick,
    _publish,
    _transition,
    _uid,
    _uuid,
)
from order_service.settings import OrderSettings

logger = logging.getLogger(__name__)

S = OrderStatus
# Used when harvest.ready had no plot location. TODO(M1): ask land for it (GET /internal/geo/...).
UNKNOWN_LOCATION = {"type": "Point", "coordinates": [0.0, 0.0]}


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


def _crop_name(crop_id: str | None) -> str:
    return (crop_id or "crop").replace("_", " ").replace("-", " ").strip().title()


def _grade_factor(grade: str | None, settings: OrderSettings) -> Decimal:
    """Price factor of a lower grade: A is the agreed grade, B and C sell for less."""
    return {"B": settings.grade_b_price_factor, "C": settings.grade_c_price_factor}.get(
        (grade or "").upper(), Decimal(1)
    )


# --- consuming land and quality events ---------------------------------------------------------


async def on_reservation_accepted(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Remember who the reservation is for and how much deposit it asks.

    TODO(M1): the land contract only carries reservationId, customerId, farmerId and deposit. The
    price of the whole crop is read from `total` when land adds it; see docs/m1-assumptions.md.
    """
    reservation_id = _uuid(payload, "reservationId", "reservation_id")
    customer_id = _uuid(payload, "customerId", "customer_id")
    farmer_id = _uuid(payload, "farmerId", "farmer_id")
    if reservation_id is None or customer_id is None or farmer_id is None:
        logger.warning("Ignoring reservation.accepted without reservation, customer or farmer")
        return
    row = await session.get(HarvestRow, reservation_id, with_for_update=True)
    if row is None:
        row = HarvestRow(
            reservation_id=reservation_id,
            customer_id=customer_id,
            farmer_id=farmer_id,
            deposit=Decimal(0),
        )
        session.add(row)
    row.customer_id, row.farmer_id = customer_id, farmer_id
    row.deposit = _money(_decimal(_pick(payload, "deposit")) or Decimal(0))
    if (total := _decimal(_pick(payload, "total", "totalAmount", "total_amount"))) is not None:
        row.total = _money(total)
    row.crop_id = _pick(payload, "cropId", "crop_id") or row.crop_id
    row.expected_qty_kg = _decimal(_pick(payload, "expectedQtyKg", "expected_qty_kg")) or (
        row.expected_qty_kg
    )
    row.updated_at = _now()


async def on_harvest_ready(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Remember the crop and where it is: that point becomes the pickup of the harvest order."""
    reservation_id = _uuid(payload, "reservationId", "reservation_id")
    customer_id = _uuid(payload, "customerId", "customer_id")
    farmer_id = _uuid(payload, "farmerId", "farmer_id")
    if reservation_id is None or customer_id is None or farmer_id is None:
        logger.warning("Ignoring harvest.ready without reservation, customer or farmer")
        return
    row = await session.get(HarvestRow, reservation_id, with_for_update=True)
    if row is None:  # reservation.accepted has not arrived (yet); events can cross
        row = HarvestRow(
            reservation_id=reservation_id,
            customer_id=customer_id,
            farmer_id=farmer_id,
            deposit=Decimal(0),
        )
        session.add(row)
    if row.status in ("ORDERED", "CANCELLED"):
        return
    row.status = "HARVEST_READY"
    row.crop_id = _pick(payload, "cropId", "crop_id") or row.crop_id
    row.expected_qty_kg = _decimal(_pick(payload, "expectedQtyKg", "expected_qty_kg")) or (
        row.expected_qty_kg
    )
    row.plot_location = _pick(payload, "plotCentroid", "plot_centroid") or row.plot_location
    row.updated_at = _now()


async def on_harvest_graded(
    session: AsyncSession, payload: dict[str, Any], settings: OrderSettings
) -> None:
    """quality.graded for a HARVEST: create the harvest order when the harvest may be sold."""
    reservation_id = _uuid(payload, "subjectId", "subject_id", "reservationId")
    row = (
        await session.get(HarvestRow, reservation_id, with_for_update=True)
        if reservation_id
        else None
    )
    if row is None:
        logger.warning("quality.graded for unknown reservation %s", reservation_id)
        return
    if row.order_id is not None or row.status == "CANCELLED":
        return  # already handled (redelivery) or the reservation is gone
    result = str(_pick(payload, "result") or "").upper()
    resolution = str(_pick(payload, "resolution") or "").upper()
    grade = str(_pick(payload, "grade") or "").upper() or None
    row.quality_result, row.quality_grade = result or None, grade
    row.updated_at = _now()
    if result == "PASS":
        factor = Decimal(1)
    elif resolution == "ACCEPT_LOWER_GRADE":
        factor = _grade_factor(grade, settings)
    else:
        row.status = "ACCEPTED"  # failed: the farmer harvests again (REHARVEST) or it is settled
        return  # by hand; land sends a new harvest.ready
    weight = _decimal(_pick(payload, "weightKg", "weight_kg"))
    await _create_harvest_order(session, row, weight, factor, grade, settings)


async def _create_harvest_order(
    session: AsyncSession,
    row: HarvestRow,
    weight: Decimal | None,
    factor: Decimal,
    grade: str | None,
    settings: OrderSettings,
) -> None:
    """One HARVEST order with one line: the graded weight at the agreed price per kg."""
    qty = weight if weight and weight > 0 else (row.expected_qty_kg or Decimal(1))
    if row.total is not None and row.expected_qty_kg:
        line_total = _money(row.total / row.expected_qty_kg * qty * factor)
    elif row.total is not None:
        line_total = _money(row.total * factor)
    else:
        # TODO(M1): land did not send the price of the crop; estimate it from the deposit
        line_total = _money(row.deposit / settings.harvest_deposit_share * factor)
        logger.warning(
            "Reservation %s has no total price, estimated %s", row.reservation_id, line_total
        )
    unit_price = _money(line_total / qty)

    now = _now()
    order_id, checkout_id = uuid4(), uuid4()
    checkout = CheckoutRow(
        id=checkout_id,
        customer_id=row.customer_id,
        payment_intent_id=row.deposit_payment_id or order_id,
        payment_status=(
            PaymentStatus.SUCCEEDED if row.deposit_paid > 0 else PaymentStatus.PENDING
        ).value,
        subtotal=line_total,
        delivery_fee=Decimal(0),
        total=line_total,
        currency="INR",
        created_at=now,
    )
    order = OrderRow(
        id=order_id,
        checkout_id=checkout_id,
        customer_id=row.customer_id,
        farm_id=None,
        farm_owner_id=row.farmer_id,
        order_type="HARVEST",
        reservation_id=row.reservation_id,
        harvest_option=None,
        status=S.PLACED.value,
        subtotal=line_total,
        delivery_fee=Decimal(0),
        total=line_total,
        currency="INR",
        delivery_address=None,
        delivery_date=None,
        created_at=now,
        updated_at=now,
    )
    order.items = [
        OrderItemRow(
            listing_id=None,
            farm_id=None,
            name=f"Harvest: {_crop_name(row.crop_id)}",
            unit="kg",
            quantity=qty,
            unit_price=unit_price,
            line_total=line_total,
            pickup_location=row.plot_location or UNKNOWN_LOCATION,
        )
    ]
    note = "Harvest passed the quality check" + (f" (grade {grade})" if grade else "")
    if factor < 1:
        note += f", accepted at a lower grade price ({factor:.0%})"
    order.events = [OrderEventRow(status=S.PLACED.value, note=note, occurred_at=now)]
    checkout.orders.append(order)
    session.add(checkout)

    row.order_id = order_id
    row.status = "ORDERED"
    if row.deposit_payment_id is not None:
        await session.execute(
            update(PaymentRow)
            .where(PaymentRow.id == row.deposit_payment_id)
            .values(order_id=order_id)
        )
    _publish(session, ev.ORDER_PLACED, order)


async def on_reservation_cancelled(session: AsyncSession, payload: dict[str, Any]) -> None:
    """The reservation was cancelled before it became an order: give the deposit back.

    TODO(M1): `reservation.cancelled` is an assumed event name (land #18 owns it).
    """
    reservation_id = _uuid(payload, "reservationId", "reservation_id")
    row = (
        await session.get(HarvestRow, reservation_id, with_for_update=True)
        if reservation_id
        else None
    )
    if row is None or row.status in ("ORDERED", "CANCELLED"):
        return
    row.status = "CANCELLED"
    row.updated_at = _now()
    refund_deposit(session, row, None)


# --- deposit payments --------------------------------------------------------------------------


async def create_deposit_intent(
    session: AsyncSession,
    user: CurrentUser,
    amount: Decimal,
    reservation_id: UUID,
    gateway: PaymentGateway,
    settings: OrderSettings,
) -> PaymentIntent:
    """POST /orders/payments/intent with kind DEPOSIT. The mock gateway takes the money at once
    (unless `mock_auto_settle` is off, then POST /orders/payments/webhook settles it)."""
    row = await session.get(HarvestRow, reservation_id)
    if row is None or str(row.customer_id) != user.id:
        # same answer for a missing and a foreign reservation: ids cannot be probed
        raise NotFound("Reservation not found or not accepted yet", code="RESERVATION_NOT_FOUND")
    if row.status in ("ORDERED", "CANCELLED"):
        raise Conflict("This reservation can no longer be paid", code="RESERVATION_NOT_PAYABLE")
    if row.deposit_paid > 0:
        raise Conflict(
            "The deposit of this reservation is already paid", code="DEPOSIT_ALREADY_PAID"
        )
    if amount != row.deposit:
        raise AppError(
            "DEPOSIT_AMOUNT_MISMATCH",
            f"The deposit of this reservation is {row.deposit}",
            422,
            details={"deposit": float(row.deposit)},
        )
    intent = PaymentRow(
        id=uuid4(),
        customer_id=_uid(user),
        kind=PaymentKind.DEPOSIT.value,
        amount=amount,
        currency="INR",
        reference_id=reservation_id,
        status=PaymentStatus.PENDING.value,
    )
    session.add(intent)
    if settings.mock_auto_settle:
        await settle_payment(session, intent, await gateway.charge(amount, amount))
    await session.commit()
    return _intent_schema(intent)


async def settle_payment(session: AsyncSession, intent: PaymentRow, succeeded: bool) -> None:
    """Mark a DEPOSIT intent SUCCEEDED or FAILED; the caller commits.

    A repeated report with the same result changes nothing (a gateway may call the webhook twice).
    """
    target = PaymentStatus.SUCCEEDED if succeeded else PaymentStatus.FAILED
    if intent.status == target.value:
        return
    if intent.status != PaymentStatus.PENDING.value:
        raise Conflict(f"This payment is already {intent.status}", code="PAYMENT_ALREADY_SETTLED")
    if intent.kind != PaymentKind.DEPOSIT.value or intent.reference_id is None:
        raise Conflict(
            "Only deposit payments are settled here; a FULL payment is taken by POST /orders",
            code="PAYMENT_NOT_SETTLEABLE",
        )
    if not succeeded:
        intent.status = PaymentStatus.FAILED.value
        return
    row = await session.get(HarvestRow, intent.reference_id, with_for_update=True)
    if row is None or row.status == "CANCELLED":
        raise Conflict("This reservation can no longer be paid", code="RESERVATION_NOT_PAYABLE")
    if row.deposit_paid > 0:
        raise Conflict(
            "The deposit of this reservation is already paid", code="DEPOSIT_ALREADY_PAID"
        )
    intent.status = PaymentStatus.SUCCEEDED.value
    row.deposit_paid = intent.amount
    row.deposit_payment_id = intent.id
    row.updated_at = _now()
    publish_payment_succeeded(session, intent, row.reservation_id)


async def apply_webhook(
    session: AsyncSession, payment_intent_id: UUID, succeeded: bool
) -> PaymentIntent:
    intent = await session.get(PaymentRow, payment_intent_id, with_for_update=True)
    if intent is None:
        raise NotFound("Payment intent not found", code="PAYMENT_INTENT_NOT_FOUND")
    await settle_payment(session, intent, succeeded)
    await session.commit()
    return _intent_schema(intent)


# --- choosing delivery or buy-back -------------------------------------------------------------


async def choose_option(
    session: AsyncSession, user: CurrentUser, body: HarvestOrderChoice, settings: OrderSettings
) -> OrderDetail:
    """POST /orders/harvest: the customer decides what happens to the graded harvest."""
    row = await session.get(HarvestRow, body.reservation_id, with_for_update=True)
    if row is None or str(row.customer_id) != user.id:
        raise NotFound("Reservation not found", code="RESERVATION_NOT_FOUND")
    if row.order_id is None:
        raise Conflict("The harvest has not passed the quality check yet", code="HARVEST_NOT_READY")
    order = await _load_order(session, row.order_id)
    if order.harvest_option is not None:
        if order.harvest_option == body.option.value:
            return await _detail(session, order.id)  # repeating the same choice is fine
        raise Conflict(
            "The option of this harvest was already chosen", code="HARVEST_OPTION_CHOSEN"
        )
    if order.status != S.PLACED:
        raise Conflict("This harvest order is closed", code="HARVEST_ORDER_CLOSED")

    order.harvest_option = body.option.value
    note = f"Customer chose {body.option.value.lower()}"
    if body.option == HarvestOption.DELIVERY:
        assert body.delivery_address is not None  # checked by the request model
        order.delivery_address = body.delivery_address.model_dump(mode="json", by_alias=True)
        order.delivery_date = _delivery_date(body.delivery_date)
        order.delivery_fee = _money(settings.delivery_fee_per_order)
        order.total = order.subtotal + order.delivery_fee
        await session.execute(
            update(CheckoutRow)
            .where(CheckoutRow.id == order.checkout_id)
            .values(delivery_fee=order.delivery_fee, total=order.total)
        )
        # already graded, so packing and the quality step are only recorded; logistics gets the order
        await _transition(session, order, S.CONFIRMED, note=note)
        await _transition(session, order, S.PACKED, note="Harvest packed by the farmer")
        await _transition(session, order, S.QC_PASSED, note="Graded before the order was created")
        await _transition(
            session,
            order,
            S.READY_FOR_DISPATCH,
            ev.ORDER_READY_FOR_DISPATCH,
            note="Ready for pickup",
        )
    else:
        credit = _money(order.subtotal * settings.buyback_rate)
        session.add(
            PaymentRow(
                id=uuid4(),
                customer_id=order.customer_id,
                kind=PaymentKind.REFUND.value,
                amount=credit,
                currency=order.currency,
                reference_id=order.reservation_id,
                order_id=order.id,
                status=PaymentStatus.SUCCEEDED.value,
            )
        )
        await _transition(session, order, S.CONFIRMED, note=note)
        await _transition(session, order, S.PACKED)
        await _transition(session, order, S.QC_PASSED)
        await _transition(session, order, S.READY_FOR_DISPATCH)
        await _transition(session, order, S.DELIVERED, note="Bought back by the farmer")
        await _transition(
            session, order, S.COMPLETED, ev.ORDER_COMPLETED, note=f"Customer credited {credit}"
        )
    await session.commit()
    return await _detail(session, order.id, refresh=True)


# --- completing a delivered harvest order ------------------------------------------------------


async def complete_delivery(session: AsyncSession, order_id: UUID, gateway: PaymentGateway) -> None:
    """delivery.completed for a HARVEST order: settle the balance, then COMPLETED.

    If the balance is declined the order stays DELIVERED and a FAILED BALANCE payment is kept.
    TODO(M1): there is no retry endpoint yet; see docs/m1-assumptions.md.
    """
    order = (
        await session.execute(select(OrderRow).where(OrderRow.id == order_id).options(*_LOAD))
    ).scalar_one_or_none()
    if order is None or OrderStatus(order.status) not in {
        S.READY_FOR_DISPATCH,
        S.POOLED,
        S.IN_TRANSIT,
        S.DELIVERED,
    }:
        logger.info("Skipping delivery.completed for order %s", order_id)
        return
    if order.status != S.DELIVERED:
        await _transition(session, order, S.DELIVERED, note="Delivered")
    row = (
        await session.get(HarvestRow, order.reservation_id, with_for_update=True)
        if order.reservation_id
        else None
    )
    held = row.deposit_paid - row.deposit_refunded if row else Decimal(0)
    balance = order.total - held
    if balance > 0:
        payment = PaymentRow(
            id=uuid4(),
            customer_id=order.customer_id,
            kind=PaymentKind.BALANCE.value,
            amount=balance,
            currency=order.currency,
            reference_id=order.reservation_id,
            order_id=order.id,
            status=PaymentStatus.PENDING.value,
        )
        session.add(payment)
        if not await gateway.charge(balance, balance):
            payment.status = PaymentStatus.FAILED.value
            order.events.append(
                OrderEventRow(
                    order_id=order.id, status=S.DELIVERED.value, note="BALANCE_PAYMENT_FAILED"
                )
            )
            return
        payment.status = PaymentStatus.SUCCEEDED.value
        publish_payment_succeeded(session, payment, order.reservation_id, [order.id])
    elif balance < 0:
        # the deposit was more than the (lower grade) price: give the difference back
        session.add(
            PaymentRow(
                id=uuid4(),
                customer_id=order.customer_id,
                kind=PaymentKind.REFUND.value,
                amount=-balance,
                currency=order.currency,
                reference_id=order.reservation_id,
                order_id=order.id,
                status=PaymentStatus.SUCCEEDED.value,
            )
        )
    await _transition(session, order, S.COMPLETED, ev.ORDER_COMPLETED, note="Balance settled")
