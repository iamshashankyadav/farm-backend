"""Alembic environment: migrations run inside the `land` schema only."""

import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from farm_common.settings import ServiceSettings
from land_service.db import SCHEMA, Base

config = context.config
config.set_main_option("sqlalchemy.url", ServiceSettings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
