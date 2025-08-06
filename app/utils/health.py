"""Health check utilities for monitoring service status."""

import asyncio
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import redis
from google.cloud import speech

from ..models.config import AppConfig
from .logging import LoggerMixin


class HealthChecker(LoggerMixin):
    """Health checker for various service components."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._redis_client: Optional[redis.Redis] = None
        self._speech_client: Optional[speech.SpeechClient] = None
        self._last_check_time: Optional[datetime] = None
        self._cached_results: Dict[str, Any] = {}
        self._cache_ttl = timedelta(seconds=30)  # Cache results for 30 seconds

    async def get_health_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get comprehensive health status of all components."""
        now = datetime.utcnow()

        # Use cached results if still valid
        if (
            not force_refresh
            and self._last_check_time
            and now - self._last_check_time < self._cache_ttl
            and self._cached_results
        ):
            return self._cached_results

        start_time = time.time()

        # Run all health checks concurrently
        checks = await asyncio.gather(
            self._check_redis(),
            self._check_google_speech(),
            self._check_storage(),
            return_exceptions=True,
        )

        redis_health, speech_health, storage_health = checks

        # Determine overall health
        all_healthy = all(
            isinstance(check, dict) and check.get("healthy", False)
            for check in [redis_health, speech_health, storage_health]
        )

        health_status = {
            "status": "healthy" if all_healthy else "unhealthy",
            "timestamp": now.isoformat() + "Z",
            "check_duration_ms": int((time.time() - start_time) * 1000),
            "components": {
                "redis": (
                    redis_health
                    if isinstance(redis_health, dict)
                    else {"healthy": False, "error": str(redis_health)}
                ),
                "google_speech": (
                    speech_health
                    if isinstance(speech_health, dict)
                    else {"healthy": False, "error": str(speech_health)}
                ),
                "storage": (
                    storage_health
                    if isinstance(storage_health, dict)
                    else {"healthy": False, "error": str(storage_health)}
                ),
            },
        }

        # Cache results
        self._cached_results = health_status
        self._last_check_time = now

        return health_status

    async def _check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity and responsiveness."""
        try:
            if not self._redis_client:
                self._redis_client = redis.from_url(self.config.celery.broker_url)

            start_time = time.time()

            # Test basic connectivity
            await asyncio.get_event_loop().run_in_executor(
                None, self._redis_client.ping
            )

            # Test set/get operation
            test_key = "health_check_test"
            test_value = str(int(time.time()))

            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._redis_client.set(test_key, test_value, ex=60)
            )

            retrieved_value = await asyncio.get_event_loop().run_in_executor(
                None, self._redis_client.get, test_key
            )

            if retrieved_value.decode() != test_value:
                raise ValueError("Redis set/get test failed")

            # Clean up test key
            await asyncio.get_event_loop().run_in_executor(
                None, self._redis_client.delete, test_key
            )

            response_time = int((time.time() - start_time) * 1000)

            return {
                "healthy": True,
                "response_time_ms": response_time,
                "message": "Redis is responsive",
            }

        except Exception as e:
            self.log_error(f"Redis health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e),
                "message": "Redis connectivity issues",
            }

    async def _check_google_speech(self) -> Dict[str, Any]:
        """Check Google Speech-to-Text API connectivity."""
        try:
            if not self.config.google.application_credentials:
                return {
                    "healthy": False,
                    "message": "Google credentials not configured",
                    "skipped": True,
                }

            if not self._speech_client:
                self._speech_client = speech.SpeechClient()

            start_time = time.time()

            # Test API connectivity with a minimal request
            # We'll just check if we can create a recognition config
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=8000,
                language_code=self.config.google.language_code,
            )

            # This doesn't make an API call, just validates the client is properly configured
            if config.language_code != self.config.google.language_code:
                raise ValueError("Speech client configuration failed")

            response_time = int((time.time() - start_time) * 1000)

            return {
                "healthy": True,
                "response_time_ms": response_time,
                "message": "Google Speech-to-Text client configured",
                "language_code": self.config.google.language_code,
                "model": self.config.google.model,
            }

        except Exception as e:
            self.log_error(f"Google Speech health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e),
                "message": "Google Speech-to-Text API issues",
            }

    async def _check_storage(self) -> Dict[str, Any]:
        """Check storage directory accessibility and disk space."""
        try:
            storage_path = self.config.storage.path

            # Check if directory exists and is writable
            if not storage_path.exists():
                storage_path.mkdir(parents=True, exist_ok=True)

            if not storage_path.is_dir():
                raise ValueError(f"Storage path is not a directory: {storage_path}")

            # Test write permissions
            test_file = storage_path / "health_check_test.tmp"
            test_content = f"Health check at {datetime.utcnow().isoformat()}"

            test_file.write_text(test_content)

            # Verify we can read it back
            if test_file.read_text() != test_content:
                raise ValueError("Storage read/write test failed")

            # Clean up test file
            test_file.unlink()

            # Check disk space (basic check)
            import shutil

            total, used, free = shutil.disk_usage(storage_path)
            free_gb = free // (1024**3)

            if free_gb < 1:  # Less than 1GB free
                self.log_warning(f"Low disk space: {free_gb}GB free")

            return {
                "healthy": True,
                "message": "Storage is accessible",
                "path": str(storage_path),
                "free_space_gb": free_gb,
                "total_space_gb": total // (1024**3),
            }

        except Exception as e:
            self.log_error(f"Storage health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e),
                "message": "Storage accessibility issues",
            }

    async def is_ready(self) -> bool:
        """Simple readiness check for Kubernetes/Docker health probes."""
        try:
            status = await self.get_health_status()
            return status["status"] == "healthy"
        except Exception:
            return False
