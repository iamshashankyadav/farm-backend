"""API-level tests for the logistics routes (requires TEST_DATABASE_URL)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from logistics_service.routing import RouteResult

_MOCK_ROUTE = RouteResult(
    total_km=8.0,
    km_saved=1.5,
    linestring_coords=[(21.0, 81.0), (21.1, 81.1)],
    waypoint_order=[0, 1],
    etas=[],
    osrm_meta={"fallback": True},
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /pools/run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pools_run_requires_admin(
    client: AsyncClient,
    delivery_headers: dict[str, str],
) -> None:
    resp = await client.post("/pools/run", headers=delivery_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pools_run_no_orders(
    client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    with (
        patch("logistics_service.routes.fetch_ready_orders", new=AsyncMock(return_value=[])),
        patch(
            "logistics_service.routes.run_pooling",
            new=AsyncMock(return_value=[]),
        ),
    ):
        resp = await client.post("/pools/run?date=2026-11-17", headers=admin_headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["poolsCreated"] == 0
    assert body["pools"] == []


# ---------------------------------------------------------------------------
# POST /location
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_location_ping(
    client: AsyncClient,
    delivery_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    resp = await client.post(
        "/location",
        json={"lat": 21.1, "lng": 81.3, "accuracyM": 10.0},
        headers=delivery_headers,
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# GET /orders/{id}/track  (unauthenticated → 401)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(f"/orders/{uuid4()}/track")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_track_unknown_order(
    client: AsyncClient,
    delivery_headers: dict[str, str],
) -> None:
    resp = await client.get(f"/orders/{uuid4()}/track", headers=delivery_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stop"] is None
    assert body["poolId"] is None


# ---------------------------------------------------------------------------
# GET /my-route  → 404 when no pool assigned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_my_route_no_pool(
    client: AsyncClient,
    delivery_headers: dict[str, str],
) -> None:
    resp = await client.get("/my-route?date=2026-11-17", headers=delivery_headers)
    assert resp.status_code == 404
