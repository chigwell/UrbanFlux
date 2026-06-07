from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "London Datastore CSV Dashboard"
    database_path: Path = BACKEND_ROOT / "data" / "london_datastore.sqlite3"
    csv_storage_dir: Path = BACKEND_ROOT / "data" / "csv"
    datastore_base_url: str = "https://data.london.gov.uk"
    request_timeout_seconds: float = 45.0
    download_request_delay_seconds: float = 1.5
    download_retry_attempts: int = 6
    download_retry_backoff_seconds: float = 3.0
    download_max_retry_after_seconds: float = 180.0
    london_borough_shape_url: str = (
        "https://data.london.gov.uk/download/20od9/2a5e50ac-c22e-4d68-89e2-85f1e0ff9057/"
        "LB_LSOA2021_shp.zip"
    )
    london_borough_bounds_tolerance: float = 0.0
    llm7_token: str | None = Field(default=None, validation_alias="LLM7_TOKEN")
    llm7_api_base_url: str = Field(
        default="https://api.llm7.io/v1",
        validation_alias="LLM7_API_BASE_URL",
    )
    llm7_model: str = Field(default="gpt-4o-mini", validation_alias="LLM7_MODEL")
    llm7_request_timeout_seconds: float = Field(
        default=90.0,
        validation_alias="LLM7_REQUEST_TIMEOUT_SECONDS",
    )
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    allowed_origin_regex: str | None = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_prefix="LONDON_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
