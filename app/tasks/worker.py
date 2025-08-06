"""Celery worker configuration and setup."""

import os
from celery import Celery
from celery.signals import worker_init, worker_shutdown, task_prerun, task_postrun

from ..models.config import AppConfig
from ..utils.logging import setup_logging, get_logger
from ..utils.correlation import set_correlation_id

# Load configuration
config = AppConfig()

# Initialize Celery app
celery_app = Celery(
    "voicemail_proxy",
    broker=config.celery.broker_url,
    backend=config.celery.result_backend,
    include=["app.tasks.email_tasks"],
)

# Configure Celery
celery_app.conf.update(
    # Task routing and queues
    task_routes={
        "process_voicemail_email": {"queue": "voicemail_processing"},
        "transcribe_audio_task": {"queue": "transcription"},
        "cleanup_files_task": {"queue": "cleanup"},
    },
    # Task execution settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task time limits
    task_time_limit=config.celery.task_time_limit,
    task_soft_time_limit=config.celery.task_time_limit - 30,
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Worker settings
    worker_concurrency=config.celery.worker_concurrency,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=True,
    # Result backend settings
    result_expires=3600,  # 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
        "visibility_timeout": 3600,
    },
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Set up logging
logger = get_logger(__name__)


@worker_init.connect
def worker_init_handler(sender=None, conf=None, **kwargs):
    """Initialize worker with logging and configuration."""
    setup_logging(level=config.logging.level, format_type=config.logging.format)

    logger.info(
        f"Celery worker initialized: {sender} (broker: {config.celery.broker_url}, concurrency: {config.celery.worker_concurrency})"
    )


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Handle worker shutdown."""
    logger.info(f"Celery worker shutting down: {sender}")


@task_prerun.connect
def task_prerun_handler(
    sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds
):
    """Set up task execution context."""
    # Extract correlation ID from task arguments if available
    correlation_id = None

    if args and len(args) > 0:
        # First argument might be a dict with correlation_id
        if isinstance(args[0], dict) and "correlation_id" in args[0]:
            correlation_id = args[0]["correlation_id"]

    if correlation_id:
        set_correlation_id(correlation_id)

    logger.info(
        f"Starting task execution: {task.name} (id: {task_id}, correlation: {correlation_id})"
    )


@task_postrun.connect
def task_postrun_handler(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    state=None,
    **kwds,
):
    """Clean up after task execution."""
    logger.info(
        f"Task execution completed: {task.name} (id: {task_id}, state: {state})"
    )


# Create Celery app instance that can be imported
def create_celery_app() -> Celery:
    """Create and return configured Celery app."""
    return celery_app


if __name__ == "__main__":
    # Start worker if run directly
    celery_app.start()
