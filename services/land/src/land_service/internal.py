"""Private geo references used by the media worker; these routes are not gateway-exposed."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from farm_common.errors import NotFound
from land_service.database import get_session
from land_service.db import Plot, PlotSeason, Reservation
from land_service.geo import geometry_json

router = APIRouter(prefix="/internal/geo", tags=["internal"])


@router.get("/plot/{plot_id}")
async def plot_geo(plot_id: UUID, session: AsyncSession = Depends(get_session)):
    plot = await session.get(Plot, plot_id)
    if plot is None or plot.status == "DELETED":
        raise NotFound("Plot not found", code="PLOT_NOT_FOUND")
    return {"point": geometry_json(plot.centroid), "boundary": geometry_json(plot.boundary)}


@router.get("/reservation/{reservation_id}")
async def reservation_geo(
    reservation_id: UUID, session: AsyncSession = Depends(get_session)
):
    reservation = await session.get(Reservation, reservation_id)
    if reservation is None:
        raise NotFound("Reservation not found", code="RESERVATION_NOT_FOUND")
    season = await session.get(PlotSeason, reservation.plot_season_id)
    plot = await session.get(Plot, season.plot_id) if season else None
    if plot is None or plot.status == "DELETED":
        raise NotFound("Plot not found", code="PLOT_NOT_FOUND")
    return {"point": geometry_json(plot.centroid), "boundary": geometry_json(plot.boundary)}
