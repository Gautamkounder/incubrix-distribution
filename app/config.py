"""All settings come from environment variables (or a .env file)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "incubrix-distribution"
    log_level: str = "INFO"
    simulation_mode: bool = True
    database_url: str = "sqlite:///./dev.db"
    http_timeout_s: float = 10.0
    public_base_url: str = "http://localhost:8000"
    callback_secret: str = "change-me"
    manifests_dir: str = "app/connectors/manifests"

    storage_backend: str = "local"  # local | s3
    local_storage_dir: str = "./storage"
    s3_endpoint_url: str = ""
    s3_public_endpoint_url: str = ""
    s3_bucket: str = "incubrix-outputs"
    s3_access_key: str = ""
    s3_secret_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
