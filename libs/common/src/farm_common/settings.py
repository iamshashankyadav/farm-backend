"""Settings every service reads from environment variables (or a local .env file)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    # Each service connects with its own database user, limited to its own schema.
    database_url: str = "postgresql+asyncpg://farm:change-me@localhost:5432/farm"
    rabbitmq_url: str = "amqp://farm:change-me@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    # Set to /api/v1/<service> behind the gateway so Swagger UI links resolve.
    root_path: str = ""
