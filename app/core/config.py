from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_mode: Literal["fixture", "pilot", "live"] = Field(default="fixture", alias="APP_MODE")
    zyte_api_key: str | None = Field(default=None, alias="ZYTE_API_KEY")
    zyte_api_url: str = Field(default="https://api.zyte.com/v1/extract", alias="ZYTE_API_URL")
    scraping_use_zyte: bool = Field(default=False, alias="SCRAPING_USE_ZYTE")
    scraping_fixture_mode: bool = Field(default=True, alias="SCRAPING_FIXTURE_MODE")
    scraping_country: str = Field(default="CA", alias="SCRAPING_COUNTRY")
    database_url: str = Field(default="sqlite:///var/car-dealer.db", alias="DATABASE_URL")
    object_store_root: str = Field(default="var/object-store", alias="OBJECT_STORE_ROOT")
    source_snapshot_retention_days: int = Field(default=90, alias="SOURCE_SNAPSHOT_RETENTION_DAYS")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_api_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta", alias="GEMINI_API_URL")
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")
    gemini_image_analysis_enabled: bool = Field(default=False, alias="GEMINI_IMAGE_ANALYSIS_ENABLED")
    image_fetch_timeout_seconds: float = Field(default=8.0, alias="IMAGE_FETCH_TIMEOUT_SECONDS")
    image_fetch_max_bytes: int = Field(default=5_000_000, alias="IMAGE_FETCH_MAX_BYTES")
    document_upload_max_bytes: int = Field(default=20_000_000, alias="DOCUMENT_UPLOAD_MAX_BYTES")
    saved_search_refresh_enabled: bool = Field(default=False, alias="SAVED_SEARCH_REFRESH_ENABLED")
    saved_search_refresh_poll_seconds: int = Field(default=3600, alias="SAVED_SEARCH_REFRESH_POLL_SECONDS")
    saved_search_refresh_batch_limit: int = Field(default=25, alias="SAVED_SEARCH_REFRESH_BATCH_LIMIT")
    saved_search_refresh_default_schedule: str = Field(default="daily", alias="SAVED_SEARCH_REFRESH_DEFAULT_SCHEDULE")
    alert_email_dry_run: bool = Field(default=True, alias="ALERT_EMAIL_DRY_RUN")
    alert_email_from: str = Field(default="alerts@car-dealer.local", alias="ALERT_EMAIL_FROM")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
