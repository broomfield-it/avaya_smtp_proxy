"""Pytest configuration and fixtures."""

import pytest
import tempfile
import shutil
from pathlib import Path
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from app.models.config import AppConfig, SMTPConfig, GoogleConfig, CeleryConfig, StorageConfig
from app.models.messages import VoicemailMessage, AudioAttachment, TranscriptionResult


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def test_config(temp_dir):
    """Create test configuration."""
    return AppConfig(
        smtp=SMTPConfig(
            host="127.0.0.1",
            port=1025,
            auth_required=False
        ),
        google=GoogleConfig(
            application_credentials=None,  # Mock in tests
            project_id="test-project",
            language_code="en-US"
        ),
        celery=CeleryConfig(
            broker_url="memory://",
            result_backend="cache+memory://"
        ),
        storage=StorageConfig(
            path=temp_dir / "storage",
            cleanup_after_hours=1
        )
    )


@pytest.fixture
def sample_wav_data():
    """Generate sample WAV file data."""
    # Minimal WAV header for testing
    return b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'


@pytest.fixture
def audio_attachment(sample_wav_data):
    """Create a sample audio attachment."""
    return AudioAttachment(
        filename="voicemail_test.wav",
        content_type="audio/wav",
        size_bytes=len(sample_wav_data),
        data=sample_wav_data
    )


@pytest.fixture
def sample_email_message(sample_wav_data):
    """Create a sample email message with audio attachment."""
    msg = MIMEMultipart()
    msg['From'] = "avaya@company.com"
    msg['To'] = "user@company.com"
    msg['Subject'] = "Voicemail from John Doe"
    msg['Message-ID'] = "<test123@company.com>"
    
    # Add body
    body = MIMEText("You have a new voicemail message.")
    msg.attach(body)
    
    # Add audio attachment
    audio_part = MIMEApplication(sample_wav_data, _subtype='wav')
    audio_part.add_header('Content-Disposition', 'attachment', filename='voicemail_test.wav')
    msg.attach(audio_part)
    
    return msg


@pytest.fixture
def voicemail_message(sample_email_message, audio_attachment):
    """Create a VoicemailMessage instance."""
    return VoicemailMessage.from_email_message(
        sample_email_message,
        correlation_id="test_123456"
    )


@pytest.fixture
def transcription_result():
    """Create a sample transcription result."""
    return TranscriptionResult(
        transcript="Hello, this is a test voicemail message.",
        confidence=0.95,
        language_code="en-US",
        alternatives=["Hello, this is a test voicemail message"],
        processing_time_ms=1500
    )


@pytest.fixture
def mock_google_speech(monkeypatch):
    """Mock Google Speech-to-Text client."""
    class MockSpeechClient:
        def recognize(self, config, audio):
            from google.cloud.speech import RecognizeResponse, SpeechRecognitionResult, SpeechRecognitionAlternative
            
            # Create mock response
            alternative = SpeechRecognitionAlternative()
            alternative.transcript = "Hello, this is a test voicemail message."
            alternative.confidence = 0.95
            
            result = SpeechRecognitionResult()
            result.alternatives = [alternative]
            
            response = RecognizeResponse()
            response.results = [result]
            
            return response
    
    def mock_speech_client():
        return MockSpeechClient()
    
    monkeypatch.setattr("google.cloud.speech.SpeechClient", mock_speech_client)


@pytest.fixture
def mock_smtp_server(monkeypatch):
    """Mock SMTP server for testing email sending."""
    class MockSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.messages_sent = []
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
        
        def starttls(self, context=None):
            pass
        
        def login(self, user, password):
            pass
        
        def send_message(self, msg, to_addrs=None):
            self.messages_sent.append({
                'message': msg,
                'to_addrs': to_addrs or []
            })
        
        def quit(self):
            pass
    
    # Store reference to mock instances for verification
    mock_instances = []
    
    def mock_smtp(*args, **kwargs):
        instance = MockSMTP(*args, **kwargs)
        mock_instances.append(instance)
        return instance
    
    monkeypatch.setattr("smtplib.SMTP", mock_smtp)
    monkeypatch.setattr("smtplib.SMTP_SSL", mock_smtp)
    
    return mock_instances


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis client."""
    class MockRedis:
        def __init__(self):
            self.data = {}
        
        def ping(self):
            return True
        
        def set(self, key, value, ex=None):
            self.data[key] = value
        
        def get(self, key):
            return self.data.get(key, b"test_value")
        
        def delete(self, key):
            self.data.pop(key, None)
    
    def mock_redis_from_url(url):
        return MockRedis()
    
    monkeypatch.setattr("redis.from_url", mock_redis_from_url)