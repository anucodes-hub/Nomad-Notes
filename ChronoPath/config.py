import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator


class Settings(BaseModel):
    app_name: str = "Nomad Notes"
    environment: str = Field(default="development")
    google_api_key: str | None = Field(default=None)
    google_cloud_project: str | None = Field(default=None)
    google_cloud_location: str = Field(default="us-central1")
    google_maps_api_key: str | None = Field(default=None)
    gcs_bucket_name: str | None = Field(default=None)
    database_url: str | None = Field(default=None)
    redis_url: str | None = Field(default=None)
    enable_audio: bool = Field(default=False)
    enable_visual: bool = Field(default=False)
    enable_evaluation: bool = Field(default=False)
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    agent_timeout_seconds: float = Field(default=10.0, gt=0)
    retry_attempts: int = Field(default=2, ge=0)
    local_auth_bypass: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_production(self):
        if self.environment.lower() == "production":
            missing = [
                name
                for name, value in {
                    "GOOGLE_API_KEY": self.google_api_key,
                    "GOOGLE_CLOUD_PROJECT": self.google_cloud_project,
                    "GOOGLE_MAPS_API_KEY": self.google_maps_api_key,
                    "GCS_BUCKET_NAME": self.gcs_bucket_name,
                    "DATABASE_URL": self.database_url,
                    "REDIS_URL": self.redis_url,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    "Missing required production settings: " + ", ".join(missing)
                )
        return self


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_local_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@lru_cache
def get_settings():
    _load_local_env()

    try:
        return Settings(
            app_name=os.getenv("APP_NAME", "Nomad Notes"),
            environment=os.getenv("ENVIRONMENT", "development"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY"),
            gcs_bucket_name=os.getenv("GCS_BUCKET_NAME"),
            database_url=os.getenv("DATABASE_URL"),
            redis_url=os.getenv("REDIS_URL"),
            enable_audio=_env_bool("ENABLE_AUDIO"),
            enable_visual=_env_bool("ENABLE_VISUAL"),
            enable_evaluation=_env_bool("ENABLE_EVALUATION"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            agent_timeout_seconds=float(os.getenv("AGENT_TIMEOUT_SECONDS", "10")),
            retry_attempts=int(os.getenv("RETRY_ATTEMPTS", "2")),
            local_auth_bypass=_env_bool("LOCAL_AUTH_BYPASS"),
        )
    except ValidationError as exc:
        raise RuntimeError(f"Invalid Nomad Notes configuration: {exc}") from exc
