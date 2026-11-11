"""Konfiguracja backendu czytana ze zmiennych środowiskowych (.env poza repo)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "postgis"
    postgres_port: int = 5432
    postgres_db: str = "railsafe"
    postgres_user: str = "railsafe"
    postgres_password: str = ""

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b"

    demo_mode: bool = True
    healthcheck_timeout_s: float = 2.0

    @property
    def database_connect_kwargs(self) -> dict[str, str | int]:
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "dbname": self.postgres_db,
            "user": self.postgres_user,
            "password": self.postgres_password,
            "connect_timeout": max(1, round(self.healthcheck_timeout_s)),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
