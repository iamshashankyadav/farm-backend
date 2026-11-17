"""Request / response bodies for the logistics API (camelCase JSON via ApiModel)."""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from farm_common.schemas import ApiModel

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StopType(StrEnum):
    PICKUP = "PICKUP"
    DROP = "DROP"


class StopStatus(StrEnum):
    PENDING = "PENDING"
    ARRIVED = "ARRIVED"
    DONE = "DONE"
    SKIPPED = "SKIPPED"


class PoolStatus(StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Shared sub-shapes
# ---------------------------------------------------------------------------


class GeoPoint(ApiModel):
    lat: float
    lng: float


class StopOut(ApiModel):
    id: UUID
    pool_id: UUID
    order_id: UUID
    stop_type: StopType
    seq: int
    lat: float
    lng: float
    address: str | None
    eta: datetime | None
    status: StopStatus
    photo_media_id: UUID | None
    otp_verified: bool
    done_at: datetime | None
    weight_kg: float | None


class PoolOut(ApiModel):
    id: UUID
    pool_date: date
    partner_id: UUID | None
    status: PoolStatus
    total_km: float | None
    km_saved: float | None
    stops: list[StopOut] = Field(default_factory=list)
    created_at: datetime
    assigned_at: datetime | None


# ---------------------------------------------------------------------------
# POST /logistics/pools/run
# ---------------------------------------------------------------------------


class PoolRunResponse(ApiModel):
    pools_created: int
    pools: list[PoolOut]


# ---------------------------------------------------------------------------
# POST /logistics/stops/{id}/pickup
# ---------------------------------------------------------------------------


class PickupIn(ApiModel):
    weight_kg: float | None = None


# ---------------------------------------------------------------------------
# POST /logistics/stops/{id}/deliver
# ---------------------------------------------------------------------------


class DeliverIn(ApiModel):
    photo_media_id: UUID = Field(description="media_id of the proof-of-delivery photo")
    otp: str = Field(min_length=4, max_length=4, description="4-digit OTP entered by customer")


# ---------------------------------------------------------------------------
# POST /logistics/location
# ---------------------------------------------------------------------------


class LocationPingIn(ApiModel):
    lat: float
    lng: float
    pool_id: UUID | None = None
    accuracy_m: float | None = None
    speed_ms: float | None = None
    heading: float | None = None


# ---------------------------------------------------------------------------
# GET /logistics/orders/{id}/track
# ---------------------------------------------------------------------------


class TrackOut(ApiModel):
    order_id: UUID
    pool_id: UUID | None
    stop: StopOut | None
    partner_lat: float | None = Field(None, description="Latest GPS lat from location pings")
    partner_lng: float | None = Field(None, description="Latest GPS lng from location pings")
    partner_updated_at: datetime | None
