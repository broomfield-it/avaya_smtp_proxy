"""Tests for service components."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from app.services.transcription import TranscriptionService
from app.services.email_processor import EmailProcessor
from app.services.file_manager import FileManager
from app.models.config import GoogleConfig, OutboundSMTPConfig, StorageConfig


class TestTranscriptionService:
    """Test TranscriptionService."""
    
    @pytest.fixture
    def transcription_service(self):
        """Create transcription service instance."""
        config = GoogleConfig(
            application_credentials=None,
            project_id="test-project",
            language_code="en-US"
        )
        return TranscriptionService(config)
    
    @pytest.mark.asyncio
    async def test_transcribe_audio_success(self, transcription_service, audio_attachment, mock_google_speech):
        """Test successful audio transcription."""
        result = await transcription_service.transcribe_audio(audio_attachment)
        
        assert result is not None
        assert result.transcript == "Hello, this is a test voicemail message."
        assert result.confidence == 0.95
        assert result.language_code == "en-US"
        assert result.processing_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_transcribe_multiple_files(self, transcription_service, audio_attachment, mock_google_speech):
        """Test transcribing multiple audio files."""
        attachments = [audio_attachment, audio_attachment]  # Same attachment twice
        
        results = await transcription_service.transcribe_multiple(attachments)
        
        assert len(results) == 2
        assert all(result is not None for result in results)
        assert all(result.transcript == "Hello, this is a test voicemail message." for result in results)
    
    def test_get_audio_encoding(self, transcription_service):
        """Test audio encoding detection."""
        from google.cloud.speech import RecognitionConfig
        
        # Test WAV
        encoding = transcription_service._get_audio_encoding("audio/wav")
        assert encoding == RecognitionConfig.AudioEncoding.LINEAR16
        
        # Test MP3
        encoding = transcription_service._get_audio_encoding("audio/mp3")
        assert encoding == RecognitionConfig.AudioEncoding.MP3
        
        # Test unknown (should default to LINEAR16)
        encoding = transcription_service._get_audio_encoding("audio/unknown")
        assert encoding == RecognitionConfig.AudioEncoding.LINEAR16


class TestEmailProcessor:
    """Test EmailProcessor."""
    
    @pytest.fixture
    def email_processor(self):
        """Create email processor instance."""
        config = OutboundSMTPConfig(
            host="smtp.test.com",
            port=587,
            user="test@example.com",
            password="password",
            use_tls=True
        )
        return EmailProcessor(config)
    
    @pytest.mark.asyncio
    async def test_enhance_and_forward_success(self, email_processor, voicemail_message, transcription_result, mock_smtp_server):
        """Test successful email enhancement and forwarding."""
        transcription_results = [transcription_result]
        
        success = await email_processor.enhance_and_forward(voicemail_message, transcription_results)
        
        assert success is True
        assert len(mock_smtp_server) > 0  # SMTP client was created
        
        # Verify message was sent
        smtp_instance = mock_smtp_server[0]
        assert len(smtp_instance.messages_sent) == 1
        
        sent_message = smtp_instance.messages_sent[0]['message']
        assert "[Transcribed]" in sent_message['Subject']
    
    @pytest.mark.asyncio
    async def test_enhance_subject_with_transcription(self, email_processor, transcription_result):
        """Test subject enhancement with transcription."""
        original_subject = "Voicemail from John"
        enhanced_subject = email_processor._enhance_subject(original_subject, [transcription_result])
        
        assert enhanced_subject == "[Transcribed] Voicemail from John"
    
    @pytest.mark.asyncio
    async def test_enhance_subject_without_transcription(self, email_processor):
        """Test subject enhancement without transcription."""
        original_subject = "Voicemail from John"
        enhanced_subject = email_processor._enhance_subject(original_subject, [None])
        
        assert enhanced_subject == "[Audio] Voicemail from John"
    
    def test_create_plain_text_body(self, email_processor, voicemail_message, transcription_result):
        """Test plain text body creation."""
        body = email_processor._create_plain_text_body(voicemail_message, [transcription_result])
        
        assert "VOICEMAIL TRANSCRIPTION" in body
        assert transcription_result.transcript in body
        assert f"Confidence: {transcription_result.confidence:.2%}" in body
    
    def test_create_html_body(self, email_processor, voicemail_message, transcription_result):
        """Test HTML body creation."""
        body = email_processor._create_html_body(voicemail_message, [transcription_result])
        
        assert "<html>" in body
        assert "Voicemail Transcription" in body
        assert transcription_result.transcript in body
        assert f"{transcription_result.confidence:.2%}" in body
    
    def test_html_escape(self, email_processor):
        """Test HTML escaping."""
        text = '<script>alert("test")</script> & "quotes"'
        escaped = email_processor._html_escape(text)
        
        assert "&lt;script&gt;" in escaped
        assert "&amp;" in escaped
        assert "&quot;" in escaped


class TestFileManager:
    """Test FileManager."""
    
    @pytest.fixture
    def file_manager(self, temp_dir):
        """Create file manager instance."""
        config = StorageConfig(
            path=temp_dir / "storage",
            cleanup_after_hours=1
        )
        return FileManager(config)
    
    @pytest.mark.asyncio
    async def test_store_voicemail_files(self, file_manager, voicemail_message):
        """Test storing voicemail files."""
        stored_files = await file_manager.store_voicemail_files(voicemail_message)
        
        assert len(stored_files) == len(voicemail_message.audio_attachments)
        
        # Verify files exist
        for filename, file_path in stored_files.items():
            assert file_path.exists()
            assert file_path.stat().st_size > 0
    
    @pytest.mark.asyncio
    async def test_cleanup_correlation_files_success(self, file_manager, voicemail_message):
        """Test successful file cleanup."""
        # First store files
        stored_files = await file_manager.store_voicemail_files(voicemail_message)
        correlation_id = voicemail_message.correlation_id
        
        # Verify files exist
        assert all(path.exists() for path in stored_files.values())
        
        # Cleanup with success
        result = await file_manager.cleanup_correlation_files(correlation_id, success=True)
        assert result is True
        
        # Verify files moved to processed directory
        processed_dir = file_manager.config.path / "processed" / correlation_id
        assert processed_dir.exists()
    
    @pytest.mark.asyncio
    async def test_cleanup_correlation_files_failure(self, file_manager, voicemail_message):
        """Test file cleanup on processing failure."""
        # First store files
        stored_files = await file_manager.store_voicemail_files(voicemail_message)
        correlation_id = voicemail_message.correlation_id
        
        # Cleanup with failure
        result = await file_manager.cleanup_correlation_files(correlation_id, success=False)
        assert result is True
        
        # Verify files moved to failed directory
        failed_dir = file_manager.config.path / "failed" / correlation_id
        assert failed_dir.exists()
    
    def test_generate_safe_filename(self, file_manager):
        """Test safe filename generation."""
        original = "voicemail with spaces & special chars!.wav"
        safe = file_manager._generate_safe_filename(original, 0)
        
        assert safe.startswith("audio_00_")
        assert safe.endswith(".wav")
        assert " " not in safe
        assert "&" not in safe
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self, file_manager, voicemail_message):
        """Test storage statistics."""
        # Store some files first
        await file_manager.store_voicemail_files(voicemail_message)
        
        stats = await file_manager.get_storage_stats()
        
        assert "storage_path" in stats
        assert "temp_files" in stats
        assert "total_size_bytes" in stats
        assert stats["temp_files"] > 0