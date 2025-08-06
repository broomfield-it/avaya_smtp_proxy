"""Health check and monitoring server."""

import asyncio
import json
from aiohttp import web, ClientSession
from typing import Dict, Any

from app.models.config import AppConfig
from app.utils.health import HealthChecker
from app.utils.logging import setup_logging, get_logger


class HealthServer:
    """HTTP server for health checks and monitoring."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.health_checker = HealthChecker(config)
        self.logger = get_logger(__name__)

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        try:
            health_status = await self.health_checker.get_health_status()

            status_code = 200 if health_status["status"] == "healthy" else 503

            return web.Response(
                text=json.dumps(health_status, indent=2),
                content_type="application/json",
                status=status_code,
            )

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")

            error_response = {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": "unknown",
            }

            return web.Response(
                text=json.dumps(error_response, indent=2),
                content_type="application/json",
                status=503,
            )

    async def readiness_check(self, request: web.Request) -> web.Response:
        """Readiness check endpoint for Kubernetes."""
        try:
            is_ready = await self.health_checker.is_ready()

            response = {
                "ready": is_ready,
                "timestamp": "unknown",  # Will be filled by health checker
            }

            status_code = 200 if is_ready else 503

            return web.Response(
                text=json.dumps(response, indent=2),
                content_type="application/json",
                status=status_code,
            )

        except Exception as e:
            self.logger.error(f"Readiness check failed: {e}")

            return web.Response(
                text=json.dumps({"ready": False, "error": str(e)}, indent=2),
                content_type="application/json",
                status=503,
            )

    async def metrics(self, request: web.Request) -> web.Response:
        """Prometheus metrics endpoint."""
        try:
            # Basic metrics - in production you'd use prometheus_client
            metrics_data = [
                "# HELP smtp_proxy_health Health status of SMTP proxy components",
                "# TYPE smtp_proxy_health gauge",
            ]

            health_status = await self.health_checker.get_health_status()

            # Convert health status to Prometheus metrics
            overall_health = 1 if health_status["status"] == "healthy" else 0
            metrics_data.append(
                f'smtp_proxy_health{{component="overall"}} {overall_health}'
            )

            for component, status in health_status.get("components", {}).items():
                health_value = 1 if status.get("healthy", False) else 0
                metrics_data.append(
                    f'smtp_proxy_health{{component="{component}"}} {health_value}'
                )

            metrics_text = "\n".join(metrics_data) + "\n"

            return web.Response(
                text=metrics_text,
                content_type="text/plain; version=0.0.4; charset=utf-8",
            )

        except Exception as e:
            self.logger.error(f"Metrics endpoint failed: {e}")

            return web.Response(
                text=f"# Error generating metrics: {e}\n",
                content_type="text/plain",
                status=500,
            )

    async def info(self, request: web.Request) -> web.Response:
        """Application info endpoint."""
        info_data = {
            "name": "SMTP Voicemail Proxy",
            "version": "1.0.0",
            "environment": self.config.environment,
            "smtp_server": {
                "host": self.config.smtp.host,
                "port": self.config.smtp.port,
                "auth_required": self.config.smtp.auth_required,
            },
            "features": {
                "transcription": bool(self.config.google.application_credentials),
                "email_forwarding": bool(self.config.outbound_smtp.host),
                "tls_support": bool(self.config.smtp.tls_cert),
            },
        }

        return web.Response(
            text=json.dumps(info_data, indent=2), content_type="application/json"
        )

    def create_app(self) -> web.Application:
        """Create aiohttp application."""
        app = web.Application()

        # Add routes
        app.router.add_get("/health", self.health_check)
        app.router.add_get("/health/live", self.health_check)
        app.router.add_get("/health/ready", self.readiness_check)
        app.router.add_get("/metrics", self.metrics)
        app.router.add_get("/info", self.info)

        return app

    async def run(self) -> None:
        """Run the health server."""
        app = self.create_app()

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(
            runner, host="0.0.0.0", port=self.config.monitoring.health_check_port
        )

        await site.start()

        self.logger.info(
            f"Health server started on port {self.config.monitoring.health_check_port}"
        )

        # Keep server running
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour
        except (KeyboardInterrupt, asyncio.CancelledError):
            self.logger.info("Health server shutting down")
        finally:
            await runner.cleanup()


async def main():
    """Main entry point for health server."""
    config = AppConfig()

    # Set up logging
    setup_logging(level=config.logging.level, format_type=config.logging.format)

    server = HealthServer(config)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
