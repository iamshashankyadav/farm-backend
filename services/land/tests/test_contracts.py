from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from farm_common.errors import AppError
from land_service.consumers import on_quality_graded
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
    boundary = polygon([
        (81.0, 21.0), (81.1, 21.1), (81.0, 21.1), (81.1, 21.0), (81.0, 21.0)
    ])
    with pytest.raises(AppError) as exc:
        polygon_to_db(boundary)
    assert exc.value.code == "INVALID_PLOT_BOUNDARY"


def test_season_end_must_follow_start():
    with pytest.raises(ValidationError):
        SeasonCreate(
            season="Kharif", start_date="2026-09-01", end_date="2026-08-01",
            price=12000, allowed_crops=["rice"],
        )


def test_reservations_track_harvest_attempts():
    column = Reservation.__table__.c.harvest_attempt
    assert column.default.arg == 0
    assert column.nullable is False


@pytest.mark.asyncio
async def test_stale_quality_report_does_not_advance_a_newer_harvest_attempt():
    reservation = SimpleNamespace(status="HARVEST_READY", harvest_attempt=2)
    session = AsyncMock()
    session.get.return_value = reservation
    event = SimpleNamespace(payload={
        "subjectType": "HARVEST",
        "subjectId": str(uuid4()),
        "attempt": 1,
        "result": "PASS",
    })

    await on_quality_graded(session, event)

    assert reservation.status == "HARVEST_READY"


@pytest.mark.asyncio
async def test_current_harvest_attempt_pass_moves_reservation_to_fulfilling():
    reservation = SimpleNamespace(status="HARVEST_READY", harvest_attempt=2)
    session = AsyncMock()
    session.get.return_value = reservation
    event = SimpleNamespace(payload={
        "subjectType": "HARVEST",
        "subjectId": str(uuid4()),
        "attempt": 2,
        "result": "PASS",
    })

    await on_quality_graded(session, event)

    assert reservation.status == "FULFILLING"
