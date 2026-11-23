"""Land tests that need PostGIS (polygons, overlap and booking rules enforced by the database).

Point TEST_DATABASE_URL at a throwaway PostGIS database, as for catalog:

    docker run -d --rm --name farm-test-db -p 55433:5432 -e POSTGRES_USER=farm \\
        -e POSTGRES_PASSWORD=change-me -e POSTGRES_DB=farm_test postgis/postgis:16-3.4
    export TEST_DATABASE_URL=postgresql+asyncpg://farm:change-me@localhost:55433/farm_test

Without it those tests are skipped locally (and fail in CI). The fixture drops and re-creates the
`land` schema with the real Alembic migrations, so never point it at real data.
"""

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from farm_common.settings import get_settings
from land_service.database import get_session
from land_service.db import OutboxEvent
from land_service.main import app
from land_service.settings import LandSettings, get_land_settings

SERVICE_DIR = Path(__file__).resolve().parents[1]
TABLES = "crop_updates, agreements, reservations, plot_seasons, plots, outbox, processed_events"

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY = _key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
PUBLIC_KEY = (
    _key.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


def token_for(user_id: UUID, *roles: str, verified: bool = True) -> dict[str, str]:
    """Authorization header signed like identity signs it; `verified` is the farmer's `fv` claim."""
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "roles": list(roles),
        "fv": verified,
        "type": "access",
        "iss": "farm-identity",
        "aud": "farm-platform",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, PRIVATE_KEY, algorithm='RS256')}"}


async def _drop_schema(url: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS land CASCADE"))
        await conn.execute(text("CREATE SCHEMA land"))
    await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        message = "set TEST_DATABASE_URL to a PostGIS database to run the land database tests"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    asyncio.run(_drop_schema(url))
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=SERVICE_DIR,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
def settings() -> LandSettings:
    return LandSettings(jwt_public_key=PUBLIC_KEY, events_enabled=False)


@pytest.fixture
async def session_factory(database_url) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, pool_size=20, max_overflow=0)
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE {', '.join(f'land.{t}' for t in TABLES.split(', '))} CASCADE")
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(settings, session_factory) -> AsyncIterator[AsyncClient]:
    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    saved = dict(app.dependency_overrides)
    app.dependency_overrides.update(
        {
            get_session: session_override,
            get_settings: lambda: settings,
            get_land_settings: lambda: settings,
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides = saved


@pytest.fixture
def outbox(session_factory):
    async def read(event_type: str | None = None) -> list[OutboxEvent]:
        async with session_factory() as session:
            query = select(OutboxEvent).order_by(OutboxEvent.occurred_at)
            if event_type:
                query = query.where(OutboxEvent.type == event_type)
            return list((await session.execute(query)).scalars())

    return read
