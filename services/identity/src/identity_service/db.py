"""Database models for the identity service live in the `identity` schema only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "identity"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
