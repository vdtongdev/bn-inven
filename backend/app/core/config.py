from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/bn-inven.db"
    storage_path: Path = Path("./data/uploads")
    cors_origins: str = "http://localhost:5173"
    max_upload_bytes: int = 12 * 1024 * 1024
    max_image_pixels: int = 30_000_000
    worker_poll_seconds: float = 2.0
    worker_max_attempts: int = 3
    ai_provider: str = "mock"
    ai_api_key: SecretStr | None = None
    ai_model: str = "nvidia/nemotron-3.5-super-vl:free"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
