"""Database models for the land service live in the `land` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "land"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
