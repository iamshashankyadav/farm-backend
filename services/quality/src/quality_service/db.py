"""Inspection and inspector-location models owned by the quality service."""
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import DateTime, Index, JSON, MetaData, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from farm_common.outbox import OutboxMixin, ProcessedEventMixin

SCHEMA = "quality"


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class InspectorLocation(Base):
    __tablename__ = "inspector_locations"
    __table_args__ = (Index("inspector_location_gix", "location", postgresql_using="gist"),)
    inspector_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    location: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    available: Mapped[bool] = mapped_column(default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "attempt", name="inspection_subject_attempt_unique"),
        Index("inspection_assignee_status_ix", "inspector_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    attempt: Mapped[int] = mapped_column(default=1, nullable=False)
    inspector_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    grade: Mapped[str | None] = mapped_column(String(1), nullable=True)
    moisture_pct: Mapped[float | None] = mapped_column(nullable=True)
    pest_found: Mapped[bool | None] = mapped_column(nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(nullable=True)
    result: Mapped[str | None] = mapped_column(String(12), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(24), nullable=True)
    media_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    location: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )
    report_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(OutboxMixin, Base):
    __tablename__ = "outbox"


class ProcessedEvent(ProcessedEventMixin, Base):
    __tablename__ = "processed_events"
