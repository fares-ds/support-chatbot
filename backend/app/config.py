"""Settings, read from SC_* environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SC_", frozen=True)

    environment: Literal["development", "production"] = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "sc"
    postgres_password: SecretStr
    postgres_db: str = "support_chatbot"

    valkey_url: str = "redis://valkey:6379/0"

    # Local model services (ADR-0028). Development may point Ollama at another server.
    tei_embed_url: str = "http://tei-embed"
    tei_rerank_url: str = "http://tei-rerank"
    ollama_url: str = "http://ollama:11434"

    # The worker: Celery with Beat, on Valkey (OPS-10, OPS-11).
    celery_visibility_timeout: int = 3600
    """Seconds before Valkey hands an unacknowledged job to another worker, so it must stay above
    the longest job. A placeholder until the M0 benchmark measures re-embedding a knowledge base
    at its 20,000-chunk limit (#17)."""
    worker_concurrency: int = 2
    worker_heartbeat_seconds: int = 30
    worker_heartbeat_stale_seconds: int = 120
    """The worker counts as down after this long without a beat: four missed beats."""

    @field_validator("postgres_password")
    @classmethod
    def _not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("must not be empty")
        return value

    @field_validator("tei_embed_url", "tei_rerank_url", "ollama_url")
    @classmethod
    def _without_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def database_url(self) -> URL:
        """For the API's async sessions."""
        return self._database_url("postgresql+asyncpg")

    @property
    def sync_database_url(self) -> URL:
        """For the worker's synchronous sessions (ADR-0024, item 8)."""
        return self._database_url("postgresql+psycopg")

    def _database_url(self, driver: str) -> URL:
        return URL.create(
            driver,
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
