"""Database models for the notification service live in the `notification` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "notification"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
