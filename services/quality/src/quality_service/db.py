"""Database models for the quality service live in the `quality` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "quality"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
