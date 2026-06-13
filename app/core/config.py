from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    zyte_api_key: str | None = Field(default=None, alias="ZYTE_API_KEY")
    zyte_api_url: str = Field(default="https://api.zyte.com/v1/extract", alias="ZYTE_API_URL")
    scraping_use_zyte: bool = Field(default=False, alias="SCRAPING_USE_ZYTE")
    scraping_fixture_mode: bool = Field(default=True, alias="SCRAPING_FIXTURE_MODE")
    scraping_country: str = Field(default="CA", alias="SCRAPING_COUNTRY")
    object_store_root: str = Field(default="var/object-store", alias="OBJECT_STORE_ROOT")
    source_snapshot_retention_days: int = Field(default=90, alias="SOURCE_SNAPSHOT_RETENTION_DAYS")
    gemini_model: str = Field(default="gemini-flash", alias="GEMINI_MODEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
