"""SMTP server implementation with async support."""

import asyncio
import ssl
from typing import Optional

from aiosmtpd.controller import Controller

from ..models.config import AppConfig
from ..utils.logging import LoggerMixin
from .handler import SMTPHandler


class SMTPServer(LoggerMixin):
    """Async SMTP server for receiving voicemail emails."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.handler = SMTPHandler(config)
        self.controller: Optional[Controller] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context if TLS is configured."""
        if not (self.config.smtp.tls_cert and self.config.smtp.tls_key):
            return None
        
        try:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(
                str(self.config.smtp.tls_cert),
                str(self.config.smtp.tls_key)
            )
            
            self.log_info(
                "TLS/SSL configured for SMTP server",
                cert_file=str(self.config.smtp.tls_cert),
                key_file=str(self.config.smtp.tls_key)
            )
            
            return context
            
        except Exception as e:
            self.log_error(f"Failed to configure TLS/SSL: {e}")
            raise
    
    async def start(self) -> None:
        """Start the SMTP server."""
        try:
            # Create SSL context if configured
            self._ssl_context = self._create_ssl_context()
            
            # Create controller with our handler
            self.controller = Controller(
                handler=self.handler,
                hostname=self.config.smtp.host,
                port=self.config.smtp.port,
                # SSL/TLS configuration
                tls_context=self._ssl_context,
                require_starttls=bool(self._ssl_context),
                # Authentication (if configured)
                auth_required=self.config.smtp.auth_required,
                auth_require_tls=bool(self._ssl_context),
                # Message size limit
                data_size_limit=self.config.smtp.max_message_size,
                # Enable UTF8 support
                enable_SMTPUTF8=True,
            )
            
            # Start the server
            self.controller.start()
            
            self.log_info(
                f"SMTP server started successfully",
                host=self.config.smtp.host,
                port=self.config.smtp.port,
                tls_enabled=bool(self._ssl_context),
                auth_required=self.config.smtp.auth_required,
                max_message_size=self.config.smtp.max_message_size
            )
            
        except Exception as e:
            self.log_error(f"Failed to start SMTP server: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the SMTP server."""
        if self.controller:
            try:
                self.controller.stop()
                self.log_info("SMTP server stopped")
            except Exception as e:
                self.log_error(f"Error stopping SMTP server: {e}")
                raise
        else:
            self.log_warning("SMTP server was not running")
    
    async def wait_for_shutdown(self) -> None:
        """Wait for server shutdown signal."""
        if self.controller:
            # Keep the server running until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                self.log_info("Shutdown signal received")
                await self.stop()
    
    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self.controller is not None and hasattr(self.controller, 'server')
    
    @property
    def server_address(self) -> tuple:
        """Get the server's bind address and port."""
        if self.is_running and self.controller.server:
            return self.controller.server.sockets[0].getsockname()
        return (self.config.smtp.host, self.config.smtp.port)