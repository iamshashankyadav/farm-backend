from functools import lru_cache

from farm_common.settings import ServiceSettings


class LogisticsSettings(ServiceSettings):
    # OSRM routing engine base URL (public demo or self-hosted)
    osrm_base_url: str = "http://router.project-osrm.org"
    # DBSCAN epsilon in kilometres
    dbscan_eps_km: float = 3.0
    # What one vehicle carries, in kg (HLD section 14: a small pickup truck, about 500 kg).
    # A cluster heavier than this is split into several pools.
    partner_capacity_kg: float = 500.0
    # At most this many customer drops in one pool (HLD section 14, step 3)
    max_drops_per_pool: int = 15
    # Outbox relay and RabbitMQ
    events_enabled: bool = True
    # Internal URL of the order service (used to fetch READY_FOR_DISPATCH orders)
    order_service_url: str = "http://order:8000"
    # Nightly pooling cron hour (UTC): 20:30 UTC is 02:00 in India, and the job pools the orders
    # due that (India) day.
    pooling_cron_hour: int = 20
    pooling_cron_minute: int = 30


@lru_cache
def get_logistics_settings() -> LogisticsSettings:
    return LogisticsSettings()
