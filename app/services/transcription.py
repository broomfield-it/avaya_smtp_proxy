"""Google Speech-to-Text transcription service."""

import asyncio
import time
from typing import Optional, List, Dict, Any
import io

from google.cloud import speech
from google.api_core import exceptions as google_exceptions

from ..models.config import GoogleConfig
from ..models.messages import TranscriptionResult, AudioAttachment
from ..utils.logging import LoggerMixin


class TranscriptionService(LoggerMixin):
    """Service for transcribing audio using Google Speech-to-Text API."""

    def __init__(self, config: GoogleConfig):
        self.config = config
        self._client: Optional[speech.SpeechClient] = None

    @property
    def client(self) -> speech.SpeechClient:
        """Get or create Speech-to-Text client."""
        if self._client is None:
            self._client = speech.SpeechClient()
        return self._client

    async def transcribe_audio(
        self, audio_attachment: AudioAttachment
    ) -> Optional[TranscriptionResult]:
        """
        Transcribe a single audio attachment.

        Args:
            audio_attachment: The audio attachment to transcribe

        Returns:
            TranscriptionResult if successful, None if failed
        """
        start_time = time.time()

        try:
            self.log_info(
                f"Starting transcription of audio file: {audio_attachment.filename} ({audio_attachment.size_bytes} bytes, {audio_attachment.content_type})"
            )

            # Prepare audio data
            audio_data = self._prepare_audio_data(audio_attachment)
            if not audio_data:
                return None

            # Create recognition config
            recognition_config = self._create_recognition_config(audio_attachment)

            # Perform transcription
            response = await self._perform_transcription(audio_data, recognition_config)

            if not response or not response.results:
                self.log_warning(
                    f"No transcription results returned for {audio_attachment.filename}"
                )
                return None

            # Process the best result
            result = response.results[0]
            alternative = result.alternatives[0]

            # Extract word timestamps if enabled
            word_timestamps = None
            if (
                self.config.enable_word_time_offsets
                and hasattr(alternative, "words")
                and alternative.words
            ):
                word_timestamps = [
                    {
                        "word": word.word,
                        "start_time": word.start_time.total_seconds(),
                        "end_time": word.end_time.total_seconds(),
                        "confidence": getattr(word, "confidence", None),
                    }
                    for word in alternative.words
                ]

            # Get alternative transcriptions
            alternatives = [
                alt.transcript
                for alt in result.alternatives[1 : self.config.max_alternatives]
            ]

            processing_time = int((time.time() - start_time) * 1000)

            transcription_result = TranscriptionResult(
                transcript=alternative.transcript,
                confidence=alternative.confidence,
                language_code=self.config.language_code,
                alternatives=alternatives,
                word_timestamps=word_timestamps,
                processing_time_ms=processing_time,
            )

            self.log_info(
                f"Transcription completed successfully: {audio_attachment.filename} ({len(alternative.transcript)} chars, {alternative.confidence:.2f} confidence, {processing_time}ms, {len(alternatives)} alternatives)"
            )

            return transcription_result

        except google_exceptions.GoogleAPIError as e:
            self.log_error(
                f"Google API error during transcription: {e} (file: {audio_attachment.filename}, code: {getattr(e, 'code', None)}, details: {getattr(e, 'details', None)})"
            )
            return None

        except Exception as e:
            self.log_error(
                f"Unexpected error during transcription: {e} (file: {audio_attachment.filename}, type: {type(e).__name__})"
            )
            return None

    async def transcribe_multiple(
        self, audio_attachments: List[AudioAttachment]
    ) -> List[Optional[TranscriptionResult]]:
        """
        Transcribe multiple audio attachments concurrently.

        Args:
            audio_attachments: List of audio attachments to transcribe

        Returns:
            List of TranscriptionResults (None for failed transcriptions)
        """
        if not audio_attachments:
            return []

        self.log_info(
            f"Starting batch transcription of {len(audio_attachments)} audio files"
        )

        # Create tasks for concurrent transcription
        tasks = [self.transcribe_audio(attachment) for attachment in audio_attachments]

        # Execute all transcriptions concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle exceptions
        transcription_results = []
        successful_count = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.log_error(
                    f"Exception in batch transcription",
                    filename=audio_attachments[i].filename,
                    error=str(result),
                )
                transcription_results.append(None)
            elif result is not None:
                transcription_results.append(result)
                successful_count += 1
            else:
                transcription_results.append(None)

        self.log_info(
            f"Batch transcription completed: {successful_count}/{len(audio_attachments)} successful"
        )

        return transcription_results

    def _prepare_audio_data(self, audio_attachment: AudioAttachment) -> Optional[bytes]:
        """
        Prepare audio data for Google Speech-to-Text API.

        Args:
            audio_attachment: The audio attachment to prepare

        Returns:
            Prepared audio data or None if preparation failed
        """
        try:
            # For now, we'll pass through the raw audio data
            # In production, you might want to add audio format conversion here
            return audio_attachment.data

        except Exception as e:
            self.log_error(
                f"Failed to prepare audio data: {e} (file: {audio_attachment.filename}, type: {audio_attachment.content_type})"
            )
            return None

    def _create_recognition_config(
        self, audio_attachment: AudioAttachment
    ) -> speech.RecognitionConfig:
        """
        Create recognition configuration for the audio.

        Args:
            audio_attachment: The audio attachment to configure for

        Returns:
            Recognition configuration
        """
        # Determine audio encoding from content type
        encoding = self._get_audio_encoding(audio_attachment.content_type)

        # Create configuration
        config = speech.RecognitionConfig(
            encoding=encoding,
            # sample_rate_hertz=16000,  # Standard rate for speech recognition
            language_code=self.config.language_code,
            model=self.config.model,
            enable_word_time_offsets=self.config.enable_word_time_offsets,
            # Note: enable_profanity_filter and enable_speaker_diarization have been deprecated
            max_alternatives=self.config.max_alternatives,
            # Enhanced features for telephony
            use_enhanced=True,
            enable_automatic_punctuation=True,
        )

        return config

    def _get_audio_encoding(
        self, content_type: str
    ) -> speech.RecognitionConfig.AudioEncoding:
        """
        Determine audio encoding from MIME content type.

        Args:
            content_type: MIME content type

        Returns:
            Google Speech-to-Text audio encoding
        """
        content_type_lower = content_type.lower()

        if "wav" in content_type_lower:
            return speech.RecognitionConfig.AudioEncoding.LINEAR16
        elif "mp3" in content_type_lower or "mpeg" in content_type_lower:
            # MP3 is supported but may be in beta - fall back to LINEAR16 for now
            self.log_warning(
                f"MP3 encoding not yet supported, using LINEAR16 instead for: {content_type}"
            )
            return speech.RecognitionConfig.AudioEncoding.LINEAR16
        elif "flac" in content_type_lower:
            return speech.RecognitionConfig.AudioEncoding.FLAC
        elif "ogg" in content_type_lower:
            return speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        elif "amr" in content_type_lower:
            return speech.RecognitionConfig.AudioEncoding.AMR
        elif "amr-wb" in content_type_lower:
            return speech.RecognitionConfig.AudioEncoding.AMR_WB
        else:
            # Default to LINEAR16 for WAV files (most common for Avaya)
            self.log_warning(
                f"Unknown audio content type, defaulting to LINEAR16: {content_type}"
            )
            return speech.RecognitionConfig.AudioEncoding.LINEAR16

    async def _perform_transcription(
        self, audio_data: bytes, config: speech.RecognitionConfig
    ) -> Optional[speech.RecognizeResponse]:
        """
        Perform the actual transcription API call.

        Args:
            audio_data: Raw audio data
            config: Recognition configuration

        Returns:
            Recognition response or None if failed
        """
        try:
            # Create audio object
            audio = speech.RecognitionAudio(content=audio_data)

            # Create recognition request
            request = speech.RecognizeRequest(config=config, audio=audio)

            # Perform synchronous recognition for files < 60 seconds
            # For longer files, we would use long_running_recognize
            response = await asyncio.get_event_loop().run_in_executor(
                None, self.client.recognize, request
            )

            return response

        except google_exceptions.InvalidArgument as e:
            self.log_error(
                f"Invalid argument for transcription: {e}", error_details=str(e)
            )
            return None

        except google_exceptions.DeadlineExceeded as e:
            self.log_error(f"Transcription timeout: {e}")
            return None

        except google_exceptions.ResourceExhausted as e:
            self.log_error(f"API quota exceeded: {e}")
            return None

        except Exception as e:
            self.log_error(f"Transcription API call failed: {e}")
            return None
