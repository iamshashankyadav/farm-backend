"""Internal routes: reachable only inside the Docker network, never through the gateway."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from order_service.db import OrderRow
from order_service.deps import get_session
from order_service.schemas import OrderStatus

router = APIRouter(prefix="/internal", tags=["internal"])


def _address_line(address: dict[str, Any]) -> str:
    parts = [
        address.get("line1"),
        address.get("line2"),
        address.get("city"),
        address.get("pincode"),
    ]
    return ", ".join(str(p) for p in parts if p)


@router.get(
    "/orders/ready-for-dispatch",
    summary="Orders logistics can pool (called by the logistics pooling job)",
)
async def ready_for_dispatch(
    pool_date: date = Query(alias="date", description="Pool orders due on or before this day"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Orders in READY_FOR_DISPATCH whose delivery date is `date` or earlier.

    The shape is what the logistics pooling job reads (snake_case keys, not the public camelCase):
    `order_id`, `hub_lat`/`hub_lng` (where the farm hands the produce over), `drop_lat`/`drop_lng`
    (the customer's address), `weight_kg` and `address`. Once logistics publishes `pool.assigned`
    the order moves to POOLED and no longer shows up here.
    TODO(M1): `weight_kg` adds up the quantities of all items whatever their unit.
    """
    rows = (
        (
            await session.execute(
                select(OrderRow)
                .where(
                    OrderRow.status == OrderStatus.READY_FOR_DISPATCH.value,
                    OrderRow.delivery_date <= pool_date,
                    OrderRow.delivery_address.is_not(None),
                )
                .options(selectinload(OrderRow.items))
                .order_by(OrderRow.created_at, OrderRow.id)
            )
        )
        .scalars()
        .all()
    )
    result = []
    for row in rows:
        if not row.items or row.delivery_address is None:
            continue
        hub_lng, hub_lat = row.items[0].pickup_location["coordinates"]
        drop_lng, drop_lat = row.delivery_address["location"]["coordinates"]
        result.append(
            {
                "order_id": str(row.id),
                "hub_lat": hub_lat,
                "hub_lng": hub_lng,
                "drop_lat": drop_lat,
                "drop_lng": drop_lng,
                "weight_kg": float(sum(i.quantity for i in row.items)),
                "address": _address_line(row.delivery_address),
            }
        )
    return result
