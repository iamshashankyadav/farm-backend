from functools import lru_cache

from farm_common.settings import ServiceSettings


class QualitySettings(ServiceSettings):
    events_enabled: bool = True


@lru_cache
def get_quality_settings() -> QualitySettings:
    return QualitySettings()
