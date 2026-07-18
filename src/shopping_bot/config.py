from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(default="")
    database_url: str = Field(default="sqlite+aiosqlite:///./shopping_bot.db")
    scan_interval_seconds: int = Field(default=43200)  # 12h — Varus updates promos ~weekly, hourly polling is overkill

    varus_default_shop_id: int = Field(default=57)
    varus_request_timeout_seconds: int = Field(default=15)

    log_level: str = Field(default="INFO")


settings = Settings()
