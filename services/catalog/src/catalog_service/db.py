"""Database models for the catalog service live in the `catalog` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "catalog"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
