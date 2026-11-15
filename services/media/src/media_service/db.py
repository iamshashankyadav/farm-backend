"""Database models for the media service live in the `media` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "media"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
