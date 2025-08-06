"""Main application entry point for SMTP server."""

import asyncio
import signal
import sys
from typing import Optional

from app.models.config import AppConfig
from app.smtp.server import SMTPServer
from app.utils.logging import setup_logging, get_logger


class Application:
    """Main application class."""

    def __init__(self):
        self.config = AppConfig()
        self.smtp_server: Optional[SMTPServer] = None
        self.logger = get_logger(__name__)
        self._shutdown_event = asyncio.Event()

    async def startup(self) -> None:
        """Start the application."""
        try:
            # Set up logging
            setup_logging(
                level=self.config.logging.level, format_type=self.config.logging.format
            )

            self.logger.info(
                f"Starting SMTP Voicemail Proxy v1.0.0 "
                f"(env: {self.config.environment}, smtp: {self.config.smtp.host}:{self.config.smtp.port})"
            )

            # Initialize and start SMTP server
            self.smtp_server = SMTPServer(self.config)
            await self.smtp_server.start()

            self.logger.info("Application startup completed successfully")

        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown the application gracefully."""
        try:
            self.logger.info("Starting graceful shutdown")

            # Stop SMTP server
            if self.smtp_server:
                await self.smtp_server.stop()

            self.logger.info("Application shutdown completed")

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            raise

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown")
            self._shutdown_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def run(self) -> None:
        """Run the application."""
        try:
            # Set up signal handlers
            self.setup_signal_handlers()

            # Start the application
            await self.startup()

            # Wait for shutdown signal
            await self._shutdown_event.wait()

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"Application error: {e}")
            sys.exit(1)
        finally:
            await self.shutdown()


async def main():
    """Main entry point."""
    app = Application()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
