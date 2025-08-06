"""Correlation ID utilities for request tracking."""

import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable to store correlation ID for the current request
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return f"req_{uuid.uuid4().hex[:12]}"


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get the correlation ID from the current context."""
    return _correlation_id.get()


def get_or_generate_correlation_id() -> str:
    """Get existing correlation ID or generate a new one."""
    correlation_id = get_correlation_id()
    if correlation_id is None:
        correlation_id = generate_correlation_id()
        set_correlation_id(correlation_id)
    return correlation_id