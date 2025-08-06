"""Celery tasks for email processing and transcription."""

import asyncio
import time
from typing import Dict, List, Optional, Any

from celery import Task
from celery.exceptions import Retry

from .worker import celery_app
from ..models.config import AppConfig
from ..models.messages import VoicemailMessage, ProcessingResult
from ..services.transcription import TranscriptionService
from ..services.email_processor import EmailProcessor
from ..services.file_manager import FileManager
from ..utils.logging import get_logger
from ..utils.correlation import set_correlation_id

# Load configuration
config = AppConfig()

# Initialize services
transcription_service = TranscriptionService(config.google)
email_processor = EmailProcessor(config.outbound_smtp)
file_manager = FileManager(config.storage)

logger = get_logger(__name__)


class BaseVoicemailTask(Task):
    """Base task class with common functionality."""

    autoretry_for = (Exception,)
    retry_kwargs = {
        "max_retries": config.celery.task_max_retries,
        "countdown": config.celery.task_retry_delay,
    }
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        correlation_id = None
        if args and len(args) > 0 and isinstance(args[0], dict):
            correlation_id = args[0].get("correlation_id")

        if correlation_id:
            set_correlation_id(correlation_id)

        logger.error(
            f"Task failed: {self.name}",
            extra={
                "task_id": task_id,
                "exception": str(exc),
                "correlation_id": correlation_id,
            },
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        correlation_id = None
        if args and len(args) > 0 and isinstance(args[0], dict):
            correlation_id = args[0].get("correlation_id")

        if correlation_id:
            set_correlation_id(correlation_id)

        logger.warning(
            f"Task retry: {self.name}",
            extra={
                "task_id": task_id,
                "retry_count": self.request.retries,
                "max_retries": self.max_retries,
                "exception": str(exc),
                "correlation_id": correlation_id,
            },
        )


@celery_app.task(bind=True, base=BaseVoicemailTask, name="process_voicemail_email")
def process_voicemail_email(self, voicemail_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main task for processing voicemail emails with transcription.

    Args:
        voicemail_data: Serialized VoicemailMessage data

    Returns:
        ProcessingResult data
    """
    start_time = time.time()

    try:
        # Reconstruct VoicemailMessage from data
        voicemail_msg = VoicemailMessage(**voicemail_data)
        correlation_id = voicemail_msg.correlation_id
        set_correlation_id(correlation_id)

        logger.info(
            f"Starting voicemail processing for {voicemail_msg.sender} with {len(voicemail_msg.audio_attachments)} audio attachments"
        )

        # Run async processing
        result = asyncio.run(_process_voicemail_async(voicemail_msg))

        processing_time = int((time.time() - start_time) * 1000)
        result.processing_time_ms = processing_time

        logger.info(
            f"Voicemail processing completed: success={result.success}, transcriptions={result.transcriptions_count}, forwarded={result.forwarded}, time={processing_time}ms"
        )

        return result.dict()

    except Exception as e:
        processing_time = int((time.time() - start_time) * 1000)

        logger.error(
            f"Voicemail processing failed: {e} (type: {type(e).__name__}, time: {processing_time}ms)"
        )

        # Create failure result
        result = ProcessingResult(
            correlation_id=voicemail_data.get("correlation_id", "unknown"),
            success=False,
            error_message=str(e),
            processing_time_ms=processing_time,
        )

        return result.dict()


async def _process_voicemail_async(voicemail_msg: VoicemailMessage) -> ProcessingResult:
    """
    Async processing of voicemail message.

    Args:
        voicemail_msg: Voicemail message to process

    Returns:
        Processing result
    """
    correlation_id = voicemail_msg.correlation_id
    transcription_results = []
    files_cleaned = False
    forwarded = False

    try:
        # Step 1: Store audio files temporarily
        if voicemail_msg.has_audio_attachments():
            stored_files = await file_manager.store_voicemail_files(voicemail_msg)

            if not stored_files:
                raise ValueError("Failed to store audio files for processing")

            logger.info(f"Stored {len(stored_files)} audio files for processing")

        # Step 2: Transcribe audio files
        if voicemail_msg.has_audio_attachments():
            logger.info(
                f"Starting transcription of {len(voicemail_msg.audio_attachments)} audio files"
            )

            transcription_results = await transcription_service.transcribe_multiple(
                voicemail_msg.audio_attachments
            )

            # Update voicemail message with transcription results
            voicemail_msg.transcription_results = [
                result for result in transcription_results if result is not None
            ]

            successful_transcriptions = len(
                [r for r in transcription_results if r is not None]
            )

            logger.info(
                f"Transcription completed: {successful_transcriptions}/{len(voicemail_msg.audio_attachments)} successful"
            )

        # Step 3: Enhance and forward email
        forwarded = await email_processor.enhance_and_forward(
            voicemail_msg, transcription_results
        )

        if not forwarded:
            raise ValueError("Failed to forward enhanced email")

        # Step 4: Clean up temporary files
        files_cleaned = await file_manager.cleanup_correlation_files(
            correlation_id, success=True
        )

        # Create success result
        result = ProcessingResult(
            correlation_id=correlation_id,
            success=True,
            transcriptions_count=len(
                [r for r in transcription_results if r is not None]
            ),
            processing_time_ms=0,  # Will be set by caller
            forwarded=forwarded,
            files_cleaned=files_cleaned,
        )

        return result

    except Exception as e:
        logger.error(
            f"Error in async voicemail processing: {e} (correlation: {correlation_id}, type: {type(e).__name__})"
        )

        # Clean up files on failure
        try:
            files_cleaned = await file_manager.cleanup_correlation_files(
                correlation_id, success=False
            )
        except Exception as cleanup_error:
            logger.error(
                f"Failed to cleanup files after processing error: {cleanup_error}"
            )

        # Create failure result
        result = ProcessingResult(
            correlation_id=correlation_id,
            success=False,
            transcriptions_count=len(
                [r for r in transcription_results if r is not None]
            ),
            error_message=str(e),
            processing_time_ms=0,  # Will be set by caller
            forwarded=forwarded,
            files_cleaned=files_cleaned,
        )

        return result


@celery_app.task(bind=True, base=BaseVoicemailTask, name="transcribe_audio_task")
def transcribe_audio_task(self, audio_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Standalone task for transcribing a single audio file.

    Args:
        audio_data: Serialized AudioAttachment data

    Returns:
        TranscriptionResult data or None if failed
    """
    try:
        from ..models.messages import AudioAttachment

        # Reconstruct AudioAttachment
        audio_attachment = AudioAttachment(**audio_data)

        logger.info(
            f"Starting standalone audio transcription: {audio_attachment.filename} ({audio_attachment.size_bytes} bytes)"
        )

        # Run transcription
        result = asyncio.run(transcription_service.transcribe_audio(audio_attachment))

        if result:
            logger.info(
                f"Standalone transcription completed: {audio_attachment.filename} ({len(result.transcript)} chars, {result.confidence:.2f} confidence)"
            )
            return result.dict()
        else:
            logger.warning(
                f"Standalone transcription failed: {audio_attachment.filename}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Error in standalone transcription task: {e} (type: {type(e).__name__})"
        )
        return None


@celery_app.task(bind=True, base=BaseVoicemailTask, name="cleanup_files_task")
def cleanup_files_task(self, correlation_id: str, success: bool = True) -> bool:
    """
    Standalone task for cleaning up files.

    Args:
        correlation_id: Correlation ID to clean up
        success: Whether the processing was successful

    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        set_correlation_id(correlation_id)

        logger.info(f"Starting file cleanup: {correlation_id} (success: {success})")

        # Run cleanup
        result = asyncio.run(
            file_manager.cleanup_correlation_files(correlation_id, success)
        )

        logger.info(f"File cleanup completed: {correlation_id} (result: {result})")

        return result

    except Exception as e:
        logger.error(
            f"Error in file cleanup task: {e} (correlation: {correlation_id}, type: {type(e).__name__})"
        )
        return False


@celery_app.task(bind=True, name="health_check_task")
def health_check_task(self) -> Dict[str, Any]:
    """
    Health check task for monitoring worker status.

    Returns:
        Health status information
    """
    try:
        return {
            "status": "healthy",
            "worker_id": self.request.id,
            "timestamp": time.time(),
            "services": {
                "transcription": bool(config.google.application_credentials),
                "email": bool(config.outbound_smtp.host),
                "storage": config.storage.path.exists(),
            },
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time(),
        }
