from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TradeGuard AI"
    environment: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./tradeguard.db"
    secret_key: str = "development-only-secret-change-me"
    access_token_ttl_minutes: int = 480
    initial_admin_email: str = "admin@tradeguard.local"
    initial_admin_password: str = "change-me-now"
    allowed_origins: str = "http://localhost:5173"
    upload_dir: str = "./uploads"
    max_upload_size_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origin_list(self) -> List[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
