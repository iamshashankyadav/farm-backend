from functools import lru_cache

from farm_common.settings import ServiceSettings


class NotificationSettings(ServiceSettings):
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    expo_access_token: str | None = None
    events_enabled: bool = True
    push_enabled: bool = True


@lru_cache
def get_notification_settings() -> NotificationSettings:
    return NotificationSettings()
