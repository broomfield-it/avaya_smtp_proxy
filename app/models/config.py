"""Configuration models using Pydantic for environment-based settings."""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class SMTPConfig(BaseSettings):
    """SMTP server configuration."""

    host: str = Field(default="0.0.0.0", description="SMTP server bind address")
    port: int = Field(default=1025, description="SMTP server port")
    auth_required: bool = Field(
        default=False, description="Require SMTP authentication"
    )
    auth_user: Optional[str] = Field(default=None, description="SMTP auth username")
    auth_password: Optional[str] = Field(default=None, description="SMTP auth password")
    tls_cert: Optional[Path] = Field(
        default=None, description="TLS certificate file path"
    )
    tls_key: Optional[Path] = Field(
        default=None, description="TLS private key file path"
    )
    max_message_size: int = Field(
        default=50 * 1024 * 1024, description="Max message size in bytes"
    )

    model_config = {"env_prefix": "SMTP_", "extra": "ignore"}

    @field_validator("tls_cert", "tls_key", mode="before")
    @classmethod
    def validate_tls_files(cls, v):
        if v and not Path(v).exists():
            raise ValueError(f"TLS file not found: {v}")
        return Path(v) if v else None


class OutboundSMTPConfig(BaseSettings):
    """Outbound SMTP server configuration for forwarding emails."""

    host: str = Field(default="localhost", description="Outbound SMTP server hostname")
    port: int = Field(default=587, description="Outbound SMTP server port")
    user: str = Field(
        default="user@example.com", description="SMTP authentication username"
    )
    password: str = Field(
        default="password", description="SMTP authentication password"
    )
    use_tls: bool = Field(default=True, description="Use TLS encryption")
    use_ssl: bool = Field(default=False, description="Use SSL encryption")
    timeout: int = Field(default=30, description="Connection timeout in seconds")

    model_config = {"env_prefix": "OUTBOUND_SMTP_", "extra": "ignore"}


class GoogleConfig(BaseSettings):
    """Google Cloud Speech-to-Text API configuration."""

    application_credentials: Optional[Path] = Field(
        default=None, description="Path to Google service account credentials JSON file"
    )
    project_id: Optional[str] = Field(
        default=None, description="Google Cloud project ID"
    )
    language_code: str = Field(
        default="en-US", description="Speech recognition language"
    )
    model: str = Field(default="telephony", description="Speech recognition model")
    enable_word_time_offsets: bool = Field(
        default=False, description="Include word timestamps"
    )
    enable_profanity_filter: bool = Field(default=True, description="Filter profanity")
    max_alternatives: int = Field(
        default=1, description="Maximum transcription alternatives"
    )

    model_config = {"env_prefix": "GOOGLE_", "extra": "ignore"}

    @field_validator("application_credentials", mode="before")
    @classmethod
    def validate_credentials_file(cls, v):
        if v and not Path(v).exists():
            raise ValueError(f"Google credentials file not found: {v}")
        return Path(v) if v else None


class CeleryConfig(BaseSettings):
    """Celery task queue configuration."""

    broker_url: str = Field(
        default="redis://redis:6379/0", description="Message broker URL"
    )
    result_backend: str = Field(
        default="redis://redis:6379/0", description="Result backend URL"
    )
    worker_concurrency: int = Field(default=4, description="Number of worker processes")
    task_max_retries: int = Field(default=3, description="Maximum task retries")
    task_retry_delay: int = Field(default=60, description="Retry delay in seconds")
    task_time_limit: int = Field(default=300, description="Task time limit in seconds")

    model_config = {"env_prefix": "CELERY_", "extra": "ignore"}


class StorageConfig(BaseSettings):
    """File storage configuration."""

    path: Path = Field(
        default=Path("/app/storage"), description="Storage directory path"
    )
    cleanup_after_hours: int = Field(
        default=24, description="Cleanup files after hours"
    )
    max_audio_size_mb: int = Field(
        default=50, description="Maximum audio file size in MB"
    )
    temp_dir: Optional[Path] = Field(
        default=None, description="Temporary directory path"
    )

    model_config = {"env_prefix": "STORAGE_", "extra": "ignore"}

    @field_validator("path", "temp_dir", mode="before")
    @classmethod
    def ensure_directory_exists(cls, v):
        if v:
            path = Path(v)
            path.mkdir(parents=True, exist_ok=True)
            return path
        return v

    @property
    def max_audio_size_bytes(self) -> int:
        """Convert max audio size to bytes."""
        return self.max_audio_size_mb * 1024 * 1024


class MonitoringConfig(BaseSettings):
    """Monitoring and observability configuration."""

    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=8080, description="Metrics server port")
    flower_port: int = Field(default=5555, description="Flower monitoring port")
    flower_basic_auth: Optional[str] = Field(
        default=None, description="Flower basic auth (user:pass)"
    )
    health_check_port: int = Field(
        default=8000, description="Health check endpoint port"
    )

    model_config = {"env_prefix": "MONITORING_", "extra": "ignore"}


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json or text)")
    correlation_header: str = Field(
        default="X-Correlation-ID", description="Correlation ID header name"
    )

    model_config = {"env_prefix": "LOG_", "extra": "ignore"}


class AppConfig(BaseSettings):
    """Main application configuration."""

    # Component configurations
    smtp: SMTPConfig = Field(default_factory=SMTPConfig)
    outbound_smtp: OutboundSMTPConfig = Field(default_factory=OutboundSMTPConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Global settings
    debug: bool = Field(default=False, description="Enable debug mode")
    environment: str = Field(default="production", description="Environment name")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def model_post_init(self, __context):
        """Post-initialization setup."""
        # Set up Google credentials environment variable
        if self.google.application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
                self.google.application_credentials
            )
