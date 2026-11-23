"""OSRM routing integration (HLD issue #19).

Calls the OSRM Trip API to get an optimised route for a list of waypoints,
then extracts:
  - route LINESTRING (decoded from the overview polyline)
  - total_km
  - per-stop ETAs (from leg durations)
  - km_saved (sum of individual hub→drop distances − pool route distance)

We call the *trip* endpoint with roundtrip=false, source=first, destination=last
so OSRM returns the best reordering while keeping the first (hub) and last stop
fixed.  For pools the caller always puts the hub first; stops can be reordered.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EARTH_KM = 6371.0


# ---------------------------------------------------------------------------
# Polyline decoder (Google / OSRM 1e-5 precision)
# ---------------------------------------------------------------------------


def _decode_polyline(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    """Decode a Google-format encoded polyline into (lat, lng) pairs."""
    factor = 10**precision
    result: list[tuple[float, float]] = []
    index = lat = lng = 0
    while index < len(encoded):
        for coord in ("lat", "lng"):
            shift = result_val = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result_val |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result_val >> 1) if result_val & 1 else result_val >> 1
            if coord == "lat":
                lat += d
            else:
                lng += d
        result.append((lat / factor, lng / factor))
    return result


# ---------------------------------------------------------------------------
# Haversine (also needed here for km_saved)
# ---------------------------------------------------------------------------


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


class RouteResult:
    """Routing result returned to the pooling engine."""

    def __init__(
        self,
        total_km: float,
        km_saved: float,
        linestring_coords: list[tuple[float, float]],  # (lat, lng) in order
        waypoint_order: list[int],  # original indices in the order returned by OSRM
        etas: list[datetime],  # ETA per waypoint in waypoint_order
        osrm_meta: dict[str, Any],
        drop_etas: dict[str, datetime] | None = None,
    ) -> None:
        self.total_km = total_km
        self.km_saved = km_saved
        self.linestring_coords = linestring_coords
        self.waypoint_order = waypoint_order
        self.etas = etas
        self.osrm_meta = osrm_meta
        # order id -> arrival time at its drop, set once the road path through the real stop order
        # is known (see apply_road_path)
        self.drop_etas = drop_etas


# ---------------------------------------------------------------------------
# OSRM call
# ---------------------------------------------------------------------------


async def get_route(
    waypoints: list[tuple[float, float]],  # (lat, lng) in original order; first = hub
    depart_at: datetime | None = None,
    osrm_base_url: str = "http://router.project-osrm.org",
    request_timeout: float = 10.0,
) -> RouteResult | None:
    """Call OSRM Trip API and return a RouteResult, or None on failure.

    `waypoints[0]` is treated as source (hub); the rest are stop destinations.
    Returns None when OSRM is unreachable or returns an error – the caller
    falls back to a straight-line estimate.
    """
    if len(waypoints) < 2:
        return None

    depart = depart_at or datetime.now(UTC)

    # Build OSRM coordinate string: "lng,lat;lng,lat;..."
    coords_str = ";".join(f"{lng},{lat}" for lat, lng in waypoints)
    url = (
        f"{osrm_base_url}/trip/v1/driving/{coords_str}"
        f"?roundtrip=false&source=first&destination=last"
        f"&overview=full&steps=false&geometries=polyline"
    )

    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("OSRM request failed (%s); using fallback distances", exc)
        return _fallback_route(waypoints, depart)

    if data.get("code") != "Ok" or not data.get("trips"):
        logger.warning("OSRM returned code=%s; using fallback", data.get("code"))
        return _fallback_route(waypoints, depart)

    trip = data["trips"][0]
    total_km = trip["distance"] / 1000.0

    # Decode overview polyline → LINESTRING coords
    linestring = _decode_polyline(trip.get("geometry", ""))

    # Waypoint order from OSRM (trips_index tells which trip each waypoint maps to)
    osrm_waypoints = data.get("waypoints", [])
    # waypoint_index = position within the trip
    order_map: list[tuple[int, int]] = [
        (wp.get("waypoint_index", i), i) for i, wp in enumerate(osrm_waypoints)
    ]
    order_map.sort()
    waypoint_order = [orig_idx for _, orig_idx in order_map]

    # ETAs: accumulate leg durations
    legs = trip.get("legs", [])
    etas: list[datetime] = [depart]
    running = depart
    for leg in legs:
        running = running + timedelta(seconds=leg.get("duration", 0))
        etas.append(running)

    # km_saved: sum of individual hub→drop straight-line distances − pool route
    hub_lat, hub_lng = waypoints[0]
    individual_km = sum(_haversine_km(hub_lat, hub_lng, lat, lng) for lat, lng in waypoints[1:])
    km_saved = max(0.0, individual_km - total_km)

    return RouteResult(
        total_km=total_km,
        km_saved=km_saved,
        linestring_coords=linestring,
        waypoint_order=waypoint_order,
        etas=etas[1:],  # skip the depart time (hub arrival = depart)
        osrm_meta={"distance_m": trip["distance"], "duration_s": trip["duration"]},
    )


# ---------------------------------------------------------------------------
# Road path through the stops in their real order
# ---------------------------------------------------------------------------


async def get_road_path(
    stops: list[tuple[float, float]],  # (lat, lng) in the exact order the partner visits them
    osrm_base_url: str = "http://router.project-osrm.org",
    request_timeout: float = 10.0,
) -> tuple[list[tuple[float, float]], float, list[float]] | None:
    """Ask OSRM for the road geometry through `stops` in the given order (Route API).

    Returns (road coords as (lat, lng), total km, duration in seconds of each leg), or None when
    OSRM is unreachable or finds no road path. Unlike get_route it never reorders anything: the
    drawn line has to pass the stops in the same order as the stop list.
    """
    if len(stops) < 2:
        return None
    coords_str = ";".join(f"{lng},{lat}" for lat, lng in stops)
    url = (
        f"{osrm_base_url}/route/v1/driving/{coords_str}"
        f"?overview=full&steps=false&geometries=polyline&continue_straight=false"
    )
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("OSRM road path request failed (%s); the app draws straight lines", exc)
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        logger.warning("OSRM road path returned code=%s", data.get("code"))
        return None
    route = data["routes"][0]
    path = _decode_polyline(route.get("geometry", ""))
    if len(path) < 2:
        return None
    return path, route["distance"] / 1000.0, [leg.get("duration", 0) for leg in route["legs"]]


# ---------------------------------------------------------------------------
# Fallback: straight-line distances, constant speed assumption
# ---------------------------------------------------------------------------

_FALLBACK_SPEED_KMH = 30.0


def _fallback_route(
    waypoints: list[tuple[float, float]],
    depart: datetime,
) -> RouteResult:
    """When OSRM is unavailable: sequential straight-line route."""
    total_km = 0.0
    etas: list[datetime] = []
    running = depart
    hub_lat, hub_lng = waypoints[0]
    individual_km = 0.0

    for i in range(1, len(waypoints)):
        p_lat, p_lng = waypoints[i - 1]
        c_lat, c_lng = waypoints[i]
        seg_km = _haversine_km(p_lat, p_lng, c_lat, c_lng)
        total_km += seg_km
        running = running + timedelta(hours=seg_km / _FALLBACK_SPEED_KMH)
        etas.append(running)
        individual_km += _haversine_km(hub_lat, hub_lng, c_lat, c_lng)

    # Simple polyline: just the waypoints themselves
    linestring = list(waypoints)
    km_saved = max(0.0, individual_km - total_km)
    waypoint_order = list(range(len(waypoints)))

    return RouteResult(
        total_km=total_km,
        km_saved=km_saved,
        linestring_coords=linestring,
        waypoint_order=waypoint_order,
        etas=etas,
        osrm_meta={"fallback": True},
    )
