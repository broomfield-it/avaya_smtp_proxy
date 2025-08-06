"""Structured logging configuration with correlation ID support."""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional

from .correlation import get_correlation_id


class CorrelationFormatter(logging.Formatter):
    """Custom formatter that includes correlation ID in log records."""

    def __init__(self, format_type: str = "json"):
        super().__init__()
        self.format_type = format_type.lower()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with correlation ID."""
        # Add correlation ID to record
        correlation_id = get_correlation_id()
        if correlation_id:
            record.correlation_id = correlation_id

        if self.format_type == "json":
            return self._format_json(record)
        else:
            return self._format_text(record)

    def _format_json(self, record: logging.LogRecord) -> str:
        """Format as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
                "correlation_id",
            }:
                log_data[key] = value

        return json.dumps(log_data, default=str)

    def _format_text(self, record: logging.LogRecord) -> str:
        """Format as human-readable text."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        correlation_part = ""

        if hasattr(record, "correlation_id"):
            correlation_part = f" [{record.correlation_id}]"

        base_msg = f"{timestamp} {record.levelname:8s} {record.name}{correlation_part}: {record.getMessage()}"

        if record.exc_info:
            base_msg += "\n" + self.formatException(record.exc_info)

        return base_msg


def setup_logging(level: str = "INFO", format_type: str = "json") -> None:
    """Set up structured logging configuration."""
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with custom formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CorrelationFormatter(format_type))

    # Configure root logger
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("aiosmtpd").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("mail.log").setLevel(logging.WARNING)  # aiosmtpd internal logs


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)


class LoggerMixin:
    """Mixin class to add logging capabilities to other classes."""

    @property
    def logger(self) -> logging.Logger:
        """Get logger instance for this class."""
        return get_logger(self.__class__.__module__ + "." + self.__class__.__name__)

    def log_info(self, message: str, **kwargs) -> None:
        """Log info message with extra context."""
        self.logger.info(message, extra=kwargs)

    def log_warning(self, message: str, **kwargs) -> None:
        """Log warning message with extra context."""
        self.logger.warning(message, extra=kwargs)

    def log_error(self, message: str, **kwargs) -> None:
        """Log error message with extra context."""
        self.logger.error(message, extra=kwargs)

    def log_debug(self, message: str, **kwargs) -> None:
        """Log debug message with extra context."""
        self.logger.debug(message, extra=kwargs)
