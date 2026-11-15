"""Database models for the logistics service live in the `logistics` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "logistics"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
