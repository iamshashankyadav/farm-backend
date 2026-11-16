from functools import lru_cache

from pydantic import Field

from farm_common.settings import ServiceSettings


class LandSettings(ServiceSettings):
    events_enabled: bool = True
    # Provisional until the team agrees the reservation deposit policy; override via env.
    deposit_rate: float = Field(default=0.20, ge=0, le=1)


@lru_cache
def get_land_settings() -> LandSettings:
    return LandSettings()
