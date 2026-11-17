"""Shared fixtures for logistics tests.

Set TEST_DATABASE_URL to run against a real PostGIS database.
Without it the DB-backed tests are skipped (or fail in CI).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from farm_common.settings import get_settings
from logistics_service.database import get_session
from logistics_service.main import app
from logistics_service.settings import LogisticsSettings, get_logistics_settings

# ---------------------------------------------------------------------------
# RSA key pair for JWT signing in tests
# ---------------------------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
PUBLIC_KEY = (
    _KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)

SERVICE_DIR = Path(__file__).resolve().parents[1]


def token_for(user_id: UUID, *roles: str) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "roles": list(roles),
        "type": "access",
        "iss": "farm-identity",
        "aud": "farm-platform",
        "exp": now + timedelta(minutes=15),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, PRIVATE_KEY, algorithm='RS256')}"}


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


async def _drop_schema(url: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS logistics CASCADE"))
    await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        msg = "set TEST_DATABASE_URL to a PostGIS database to run logistics tests"
        if os.environ.get("CI"):
            pytest.fail(msg)
        pytest.skip(msg)
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
def settings() -> LogisticsSettings:
    return LogisticsSettings(
        jwt_public_key=PUBLIC_KEY,
        events_enabled=False,
    )


@pytest.fixture
async def session_factory(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, pool_size=10)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE logistics.delivery_pools, logistics.pool_stops, "
                "logistics.location_pings, logistics.outbox, "
                "logistics.processed_events CASCADE"
            )
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(
    settings: LogisticsSettings,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    saved = dict(app.dependency_overrides)
    app.dependency_overrides.update(
        {
            get_session: session_override,
            get_settings: lambda: settings,
            get_logistics_settings: lambda: settings,
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides = saved


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return token_for(uuid4(), "admin")


@pytest.fixture
def delivery_headers() -> dict[str, str]:
    return token_for(uuid4(), "delivery")


@pytest.fixture
def make_token():
    return token_for
