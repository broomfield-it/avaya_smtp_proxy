"""Data models and structures for the SMTP proxy service."""

from .config import (
    SMTPConfig,
    GoogleConfig,
    CeleryConfig,
    StorageConfig,
    AppConfig,
)
from .messages import (
    VoicemailMessage,
    TranscriptionResult,
    ProcessingResult,
)

__all__ = [
    "SMTPConfig",
    "GoogleConfig", 
    "CeleryConfig",
    "StorageConfig",
    "AppConfig",
    "VoicemailMessage",
    "TranscriptionResult",
    "ProcessingResult",
]