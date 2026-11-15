"""Database models for the order service live in the `order` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "order"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
