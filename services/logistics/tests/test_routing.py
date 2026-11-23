"""Unit tests for the OSRM routing module (no network, no DB required)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from logistics_service.routing import (
    RouteResult,
    _decode_polyline,
    _fallback_route,
    _haversine_km,
    get_route,
)


class TestDecodePolyline:
    def test_empty(self) -> None:
        assert _decode_polyline("") == []

    def test_single_point(self) -> None:
        # Encode (0, 0) in Google polyline format
        encoded = "_ibE_seK"  # (1.0, 1.0) in polyline format
        coords = _decode_polyline(encoded)
        assert len(coords) == 1

    def test_round_trip(self) -> None:
        # (38.5, -120.2) encodes as "_p~iF~ps|U" in Google's example
        coords = _decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        assert len(coords) == 3
        assert abs(coords[0][0] - 38.5) < 0.001


class TestHaversineKm:
    def test_zero(self) -> None:
        assert _haversine_km(0, 0, 0, 0) == 0.0

    def test_symmetry(self) -> None:
        a = _haversine_km(21.1, 81.3, 21.5, 81.6)
        b = _haversine_km(21.5, 81.6, 21.1, 81.3)
        assert abs(a - b) < 1e-9


class TestFallbackRoute:
    def test_two_waypoints(self) -> None:
        waypoints = [(21.1, 81.3), (21.2, 81.4)]
        depart = datetime(2026, 11, 17, 6, 0, tzinfo=UTC)
        result = _fallback_route(waypoints, depart)
        assert isinstance(result, RouteResult)
        assert result.total_km > 0
        assert len(result.etas) == 1
        assert result.osrm_meta.get("fallback") is True

    def test_km_saved_non_negative(self) -> None:
        waypoints = [(21.0, 81.0), (21.05, 81.05), (21.1, 81.1)]
        depart = datetime(2026, 11, 17, 6, 0, tzinfo=UTC)
        result = _fallback_route(waypoints, depart)
        assert result.km_saved >= 0


class TestGetRoute:
    @pytest.mark.asyncio
    async def test_osrm_success(self) -> None:
        """Mock a successful OSRM response."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "code": "Ok",
            "trips": [
                {
                    "distance": 15000,
                    "duration": 1800,
                    "geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                    "legs": [{"duration": 900}, {"duration": 900}],
                }
            ],
            "waypoints": [
                {"waypoint_index": 0},
                {"waypoint_index": 1},
                {"waypoint_index": 2},
            ],
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            waypoints = [(21.1, 81.3), (21.2, 81.4), (21.3, 81.5)]
            result = await get_route(waypoints, osrm_base_url="http://mock-osrm")

        assert result is not None
        assert abs(result.total_km - 15.0) < 0.001
        assert len(result.etas) == 2

    @pytest.mark.asyncio
    async def test_osrm_failure_falls_back(self) -> None:
        """When OSRM is unreachable, fall back to straight-line."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            waypoints = [(21.1, 81.3), (21.5, 81.6)]
            result = await get_route(waypoints, osrm_base_url="http://mock-osrm")

        assert result is not None
        assert result.osrm_meta.get("fallback") is True

    @pytest.mark.asyncio
    async def test_single_waypoint_returns_none(self) -> None:
        result = await get_route([(21.1, 81.3)])
        assert result is None


class TestGetRoadPath:
    @staticmethod
    def _client(response: MagicMock | Exception) -> MagicMock:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        if isinstance(response, Exception):
            mock_client.get = AsyncMock(side_effect=response)
        else:
            mock_client.get = AsyncMock(return_value=response)
        return mock_client

    @pytest.mark.asyncio
    async def test_routes_through_stops_in_the_given_order(self) -> None:
        from logistics_service.routing import get_road_path

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": 12000,
                    "geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                    "legs": [{"duration": 600}, {"duration": 300}],
                }
            ],
        }
        client = self._client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            result = await get_road_path(
                [(21.1, 81.3), (21.2, 81.4), (21.3, 81.5)], osrm_base_url="http://mock-osrm"
            )
        assert result is not None
        path, km, legs = result
        assert len(path) == 3 and abs(km - 12.0) < 1e-9 and legs == [600, 300]
        url = client.get.call_args.args[0]
        assert "/route/v1/driving/81.3,21.1;81.4,21.2;81.5,21.3" in url

    @pytest.mark.asyncio
    async def test_unreachable_returns_none(self) -> None:
        from logistics_service.routing import get_road_path

        with patch("httpx.AsyncClient", return_value=self._client(Exception("down"))):
            assert await get_road_path([(21.1, 81.3), (21.2, 81.4)]) is None

    @pytest.mark.asyncio
    async def test_no_route_returns_none(self) -> None:
        from logistics_service.routing import get_road_path

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"code": "NoRoute"}
        with patch("httpx.AsyncClient", return_value=self._client(resp)):
            assert await get_road_path([(21.1, 81.3), (21.2, 81.4)]) is None


class TestApplyRoadPath:
    @pytest.mark.asyncio
    async def test_line_follows_pickups_then_drops_and_etas_come_from_legs(self) -> None:
        from logistics_service.pooling import apply_road_path

        cluster = [
            {"order_id": "a", "hub_lat": 21.0, "hub_lng": 81.0, "drop_lat": 21.1, "drop_lng": 81.1},
            {"order_id": "b", "hub_lat": 21.0, "hub_lng": 81.0, "drop_lat": 21.2, "drop_lng": 81.2},
        ]
        depart = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
        trip = RouteResult(9.0, 1.0, [(0, 0), (1, 1)], [0, 1, 2], [depart, depart], {})
        calls: list[list[tuple[float, float]]] = []

        async def fake_path(points, osrm_base_url):  # type: ignore[no-untyped-def]
            calls.append(points)
            return [(21.0, 81.0), (21.2, 81.2)], 20.0, [0, 600, 600]

        with patch("logistics_service.pooling.get_road_path", fake_path):
            out = await apply_road_path(trip, cluster, depart, "http://x")

        assert out is not None
        # two pickups first, then the two drops
        assert [p[0] for p in calls[0]] == [21.0, 21.0, 21.1, 21.2]
        assert out.total_km == 20.0 and out.osrm_meta["stops_in_order"] is True
        assert out.drop_etas is not None
        assert (out.drop_etas["a"] - depart).total_seconds() == 600
        assert (out.drop_etas["b"] - depart).total_seconds() == 1200

    @pytest.mark.asyncio
    async def test_failure_keeps_the_trip_route(self) -> None:
        from logistics_service.pooling import apply_road_path

        cluster = [
            {"order_id": "a", "hub_lat": 21.0, "hub_lng": 81.0, "drop_lat": 21.1, "drop_lng": 81.1}
        ]
        depart = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
        trip = RouteResult(9.0, 1.0, [], [0, 1], [depart], {})
        with patch("logistics_service.pooling.get_road_path", AsyncMock(return_value=None)):
            out = await apply_road_path(trip, cluster, depart, "http://x")
        assert out is trip and "stops_in_order" not in out.osrm_meta
