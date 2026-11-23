from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from farm_common.errors import AppError
from land_service import routes as land_routes
from land_service.consumers import on_harvest_order
from land_service.db import Reservation
from land_service.geo import polygon_to_db
from land_service.schemas import Polygon, SeasonCreate


def polygon(points):
    return Polygon(coordinates=[points])


def test_polygon_requires_closed_wgs84_ring():
    with pytest.raises(ValidationError):
        polygon([(81.0, 21.0), (81.1, 21.0), (81.1, 21.1), (81.0, 21.1)])


def test_polygon_rejects_out_of_range_coordinates():
    with pytest.raises(ValidationError):
        polygon([(181.0, 21.0), (181.1, 21.0), (181.1, 21.1), (181.0, 21.1), (181.0, 21.0)])


def test_polygon_rejects_self_intersection():
    boundary = polygon([(81.0, 21.0), (81.1, 21.1), (81.0, 21.1), (81.1, 21.0), (81.0, 21.0)])
    with pytest.raises(AppError) as exc:
        polygon_to_db(boundary)
    assert exc.value.code == "INVALID_PLOT_BOUNDARY"


def test_season_end_must_follow_start():
    with pytest.raises(ValidationError):
        SeasonCreate(
            season="Kharif",
            start_date="2026-09-01",
            end_date="2026-08-01",
            price=12000,
            allowed_crops=["rice"],
        )


def test_reservations_track_harvest_attempts():
    column = Reservation.__table__.c.harvest_attempt
    assert column.default.arg == 0
    assert column.nullable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "before", "after"),
    [
        ("order.placed", "HARVEST_READY", "FULFILLING"),
        ("order.completed", "FULFILLING", "COMPLETED"),
        ("order.cancelled", "FULFILLING", "CANCELLED"),
        ("order.placed", "COMPLETED", "COMPLETED"),  # a late event never moves it back
    ],
)
async def test_harvest_orders_move_the_reservation(event_type, before, after):
    reservation = SimpleNamespace(status=before)
    session = AsyncMock()
    session.get.return_value = reservation
    event = SimpleNamespace(
        type=event_type, payload={"orderType": "HARVEST", "reservationId": str(uuid4())}
    )

    await on_harvest_order(session, event)

    assert reservation.status == after


@pytest.mark.asyncio
async def test_produce_orders_do_not_concern_land():
    session = AsyncMock()
    event = SimpleNamespace(type="order.placed", payload={"orderType": "PRODUCE"})

    await on_harvest_order(session, event)

    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_cancelling_reservation_publishes_event_for_deposit_refund(monkeypatch):
    customer_id = uuid4()
    reservation = SimpleNamespace(
        id=uuid4(),
        plot_season_id=uuid4(),
        customer_id=customer_id,
        farmer_id=uuid4(),
        crop_id="tomato",
        expected_qty_kg=10,
        deposit=20,
        total=100,
        status="ACTIVE",
        expires_at=datetime.now(UTC),
    )
    user = SimpleNamespace(id=str(customer_id), has_any=lambda *_: False)
    session = AsyncMock()
    session.get.return_value = reservation
    published = []

    monkeypatch.setattr(
        land_routes,
        "add_event",
        lambda _session, _model, event: published.append(event),
    )
    monkeypatch.setattr(land_routes, "reservation_out", lambda row: row)

    await land_routes.cancel_reservation(reservation.id, user, session)

    assert reservation.status == "CANCELLED"
    assert len(published) == 1
    assert published[0].type == "reservation.cancelled"
    assert published[0].payload == {
        "reservationId": str(reservation.id),
        "customerId": str(customer_id),
        "farmerId": str(reservation.farmer_id),
        "cropId": "tomato",
        "cancelledBy": "customer",
    }
    session.commit.assert_awaited_once()
