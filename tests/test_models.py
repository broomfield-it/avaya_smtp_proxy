"""Tests for data models."""

import pytest
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from app.models.messages import VoicemailMessage, AudioAttachment, TranscriptionResult
from app.models.config import AppConfig, SMTPConfig


class TestAudioAttachment:
    """Test AudioAttachment model."""
    
    def test_create_audio_attachment(self, sample_wav_data):
        """Test creating an audio attachment."""
        attachment = AudioAttachment(
            filename="test.wav",
            content_type="audio/wav",
            size_bytes=len(sample_wav_data),
            data=sample_wav_data
        )
        
        assert attachment.filename == "test.wav"
        assert attachment.content_type == "audio/wav"
        assert attachment.size_bytes == len(sample_wav_data)
        assert attachment.data == sample_wav_data
    
    def test_invalid_content_type(self, sample_wav_data):
        """Test validation of content type."""
        with pytest.raises(ValueError, match="Invalid audio content type"):
            AudioAttachment(
                filename="test.txt",
                content_type="text/plain",
                size_bytes=len(sample_wav_data),
                data=sample_wav_data
            )


class TestTranscriptionResult:
    """Test TranscriptionResult model."""
    
    def test_create_transcription_result(self):
        """Test creating a transcription result."""
        result = TranscriptionResult(
            transcript="Hello world",
            confidence=0.95,
            language_code="en-US",
            processing_time_ms=1500
        )
        
        assert result.transcript == "Hello world"
        assert result.confidence == 0.95
        assert result.language_code == "en-US"
        assert result.processing_time_ms == 1500
    
    def test_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence
        result = TranscriptionResult(
            transcript="Test",
            confidence=0.5,
            language_code="en-US",
            processing_time_ms=1000
        )
        assert result.confidence == 0.5
        
        # Invalid confidence (too high)
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            TranscriptionResult(
                transcript="Test",
                confidence=1.5,
                language_code="en-US",
                processing_time_ms=1000
            )
        
        # Invalid confidence (negative)
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            TranscriptionResult(
                transcript="Test",
                confidence=-0.1,
                language_code="en-US",
                processing_time_ms=1000
            )


class TestVoicemailMessage:
    """Test VoicemailMessage model."""
    
    def test_create_from_email_message(self, sample_email_message):
        """Test creating VoicemailMessage from EmailMessage."""
        voicemail = VoicemailMessage.from_email_message(
            sample_email_message,
            correlation_id="test_123"
        )
        
        assert voicemail.correlation_id == "test_123"
        assert voicemail.sender == "avaya@company.com"
        assert "user@company.com" in voicemail.recipients
        assert voicemail.subject == "Voicemail from John Doe"
        assert voicemail.message_id == "<test123@company.com>"
    
    def test_has_audio_attachments(self, voicemail_message):
        """Test checking for audio attachments."""
        assert voicemail_message.has_audio_attachments()
    
    def test_get_total_audio_size(self, voicemail_message):
        """Test calculating total audio size."""
        total_size = voicemail_message.get_total_audio_size()
        assert total_size > 0
        assert total_size == sum(att.size_bytes for att in voicemail_message.audio_attachments)
    
    def test_empty_voicemail(self):
        """Test voicemail without audio attachments."""
        voicemail = VoicemailMessage(
            correlation_id="test_empty",
            message_id="<empty@test.com>",
            sender="test@example.com",
            recipients=["user@example.com"],
            subject="Test message"
        )
        
        assert not voicemail.has_audio_attachments()
        assert voicemail.get_total_audio_size() == 0


class TestAppConfig:
    """Test application configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = AppConfig()
        
        assert config.smtp.host == "0.0.0.0"
        assert config.smtp.port == 1025
        assert config.smtp.auth_required is False
        assert config.google.language_code == "en-US"
        assert config.celery.worker_concurrency == 4
    
    def test_smtp_config_validation(self):
        """Test SMTP configuration validation."""
        smtp_config = SMTPConfig(
            host="localhost",
            port=587,
            auth_required=True,
            auth_user="test",
            auth_password="password"
        )
        
        assert smtp_config.host == "localhost"
        assert smtp_config.port == 587
        assert smtp_config.auth_required is True
        assert smtp_config.auth_user == "test"
        assert smtp_config.auth_password == "password"