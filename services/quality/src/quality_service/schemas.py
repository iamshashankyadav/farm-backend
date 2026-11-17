from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from farm_common.schemas import ApiModel


class Point(ApiModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]

    @model_validator(mode="after")
    def valid_coordinates(self):
        lng, lat = self.coordinates
        if not -180 <= lng <= 180 or not -90 <= lat <= 90:
            raise ValueError("coordinates must be WGS84 [longitude, latitude]")
        return self


class InspectorLocationIn(ApiModel):
    location: Point
    available: bool = True


class InspectionReport(ApiModel):
    grade: Literal["A", "B", "C"]
    moisture_pct: float = Field(ge=0, le=100)
    pest_found: bool
    weight_kg: float = Field(gt=0)
    result: Literal["PASS", "FAIL"]
    resolution: Literal["REHARVEST", "ACCEPT_LOWER_GRADE"] | None = None
    accepted_grade: Literal["A", "B", "C"] | None = None
    media_ids: list[UUID] = Field(default_factory=list, max_length=10)
    location: Point | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_failure_resolution(self):
        if self.result == "FAIL" and self.resolution is None:
            raise ValueError("A failed inspection must choose REHARVEST or ACCEPT_LOWER_GRADE")
        if self.resolution == "ACCEPT_LOWER_GRADE" and self.accepted_grade is None:
            raise ValueError("accepted_grade is required when accepting a lower grade")
        if self.resolution == "ACCEPT_LOWER_GRADE" and self.accepted_grade is not None:
            rank = {"A": 3, "B": 2, "C": 1}
            if rank[self.accepted_grade] >= rank[self.grade]:
                raise ValueError("accepted_grade must be lower than the inspected grade")
        if self.result == "PASS" and self.resolution is not None:
            raise ValueError("resolution is only valid for failed inspections")
        return self


class InspectionOut(ApiModel):
    id: UUID
    subject_type: str
    subject_id: UUID
    attempt: int
    inspector_id: UUID | None
    status: str
    grade: str | None
    moisture_pct: float | None
    pest_found: bool | None
    weight_kg: float | None
    result: str | None
    resolution: str | None
    media_ids: list[str]
    created_at: datetime
    reported_at: datetime | None
