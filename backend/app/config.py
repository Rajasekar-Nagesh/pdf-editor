"""Application settings, loaded from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- General ---
    app_name: str = "PDFDesk"
    environment: str = "production"  # "development", "production" or "test"
    public_url: str = "http://localhost:8080"  # used to build links in emails
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # --- Security ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    password_reset_expire_minutes: int = 60

    # --- Database ---
    database_url: str = "postgresql+psycopg://pdfdesk:pdfdesk@db:5432/pdfdesk"

    # --- Redis / jobs ---
    redis_url: str = "redis://redis:6379/0"
    # "queue" sends jobs to the RQ worker; "sync" runs them in-process (tests / dev without Redis)
    job_mode: str = "queue"
    job_timeout_seconds: int = 900

    # --- Storage ---
    storage_backend: str = "s3"  # "s3" or "local"
    local_storage_dir: str = "/data/files"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "pdfdesk"
    s3_region: str = "us-east-1"

    # --- Uploads ---
    max_upload_mb: int = 100
    guest_file_ttl_minutes: int = 60

    # --- Rate limiting (requests per minute per IP) ---
    rate_limit_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10

    # --- External tool timeouts (seconds) ---
    libreoffice_timeout: int = 180
    ghostscript_timeout: int = 300
    ocr_timeout: int = 900
    chromium_timeout: int = 60
    verapdf_timeout: int = 180
    verapdf_path: str = "verapdf"

    # --- Email ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "PDFDesk <no-reply@example.com>"
    smtp_starttls: bool = True

    # --- Signature requests ---
    signature_reminder_days: int = 3

    # --- AI assistant ---
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_max_context_chars: int = 400_000

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
