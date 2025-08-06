"""Celery worker entry point."""

import sys
from app.tasks.worker import celery_app
from app.models.config import AppConfig
from app.utils.logging import setup_logging

def main():
    """Main entry point for Celery worker."""
    # Load configuration
    config = AppConfig()
    
    # Set up logging
    setup_logging(
        level=config.logging.level,
        format_type=config.logging.format
    )
    
    # Start Celery worker
    celery_app.start(sys.argv[1:])


if __name__ == "__main__":
    main()