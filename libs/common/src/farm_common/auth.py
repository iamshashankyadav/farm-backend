"""JWT verification and role checks, used by every service.

The identity service signs access tokens with its RS256 private key; every other service verifies
them here with the public key. Usage in a route:

    @router.post("/listings")
    async def create_listing(user: CurrentUser = Depends(require_roles(Role.FARMER))): ...
"""

from collections.abc import Callable, Coroutine
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from farm_common.errors import Forbidden, Unauthorized
from farm_common.settings import ServiceSettings, get_settings


class Role(StrEnum):
    FARMER = "farmer"
    CUSTOMER = "customer"
    DELIVERY = "delivery"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    id: str
    roles: list[Role]
    # True once an admin verified this farmer (claim `fv` of the access token). Only verified
    # farmers may sell produce or offer land; see require_verified_farmer().
    farmer_verified: bool = False

    def has_any(self, *roles: Role) -> bool:
        return any(role in self.roles for role in roles)


@lru_cache
def _read_key(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def public_key(settings: ServiceSettings) -> str:
    if settings.jwt_public_key:
        return settings.jwt_public_key
    if settings.jwt_public_key_path:
        return _read_key(settings.jwt_public_key_path)
    raise RuntimeError("Set JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH to verify tokens")


def decode_access_token(token: str, settings: ServiceSettings) -> CurrentUser:
    try:
        claims = jwt.decode(
            token,
            public_key(settings),
            algorithms=["RS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Token has expired", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid token", code="INVALID_TOKEN") from exc
    if claims.get("type") != "access":
        raise Unauthorized("An access token is required", code="INVALID_TOKEN")
    try:
        return CurrentUser(
            id=str(claims["sub"]),
            roles=claims.get("roles", []),
            farmer_verified=bool(claims.get("fv", False)),
        )
    except ValueError as exc:
        raise Unauthorized("Invalid token", code="INVALID_TOKEN") from exc


_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: ServiceSettings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized()
    return decode_access_token(credentials.credentials, settings)


def require_roles(*roles: Role) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """Dependency that allows the request only if the user has at least one of `roles`."""

    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_any(*roles):
            raise Forbidden(f"Requires one of the roles: {', '.join(roles)}")
        return user

    return dependency


def require_verified_farmer() -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """A farmer an admin has verified (or an admin). An unverified farmer gets 403
    FARMER_NOT_VERIFIED, so nobody sells produce or offers land before the admin checks them."""

    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.has_any(Role.ADMIN):
            return user
        if not user.has_any(Role.FARMER):
            raise Forbidden(f"Requires one of the roles: {Role.FARMER}")
        if not user.farmer_verified:
            raise Forbidden(
                "Your farmer account is waiting for an admin to verify it",
                code="FARMER_NOT_VERIFIED",
            )
        return user

    return dependency
