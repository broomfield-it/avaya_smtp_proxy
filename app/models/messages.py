"""Message and result data models."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from email.message import EmailMessage

from pydantic import BaseModel, Field, field_validator


class AudioAttachment(BaseModel):
    """Represents an audio attachment from an email."""

    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME content type")
    size_bytes: int = Field(..., description="File size in bytes")
    data: bytes = Field(..., description="Raw audio data")

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("content_type")
    @classmethod
    def validate_audio_type(cls, v):
        """Ensure content type is audio."""
        if not v.startswith("audio/"):
            raise ValueError(f"Invalid audio content type: {v}")
        return v


class TranscriptionResult(BaseModel):
    """Result from Google Speech-to-Text API."""

    transcript: str = Field(..., description="Transcribed text")
    confidence: float = Field(..., description="Confidence score (0.0-1.0)")
    language_code: str = Field(..., description="Detected/used language code")
    alternatives: List[str] = Field(
        default_factory=list, description="Alternative transcriptions"
    )
    word_timestamps: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Word-level timestamps"
    )
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class VoicemailMessage(BaseModel):
    """Represents a voicemail email message."""

    # Identification
    correlation_id: str = Field(..., description="Unique correlation ID for tracking")
    message_id: str = Field(..., description="Email Message-ID header")

    # Email metadata
    sender: str = Field(..., description="Sender email address")
    recipients: List[str] = Field(..., description="List of recipient email addresses")
    subject: str = Field(..., description="Email subject line")
    received_at: datetime = Field(
        default_factory=datetime.utcnow, description="When email was received"
    )

    # Content
    body_text: Optional[str] = Field(default=None, description="Plain text email body")
    body_html: Optional[str] = Field(default=None, description="HTML email body")
    headers: Dict[str, str] = Field(default_factory=dict, description="Email headers")

    # Attachments
    audio_attachments: List[AudioAttachment] = Field(
        default_factory=list, description="Audio attachments"
    )
    other_attachments: List[Dict[str, Any]] = Field(
        default_factory=list, description="Non-audio attachments"
    )

    # Processing
    transcription_results: List[TranscriptionResult] = Field(
        default_factory=list, description="Transcription results"
    )
    processed_at: Optional[datetime] = Field(
        default=None, description="When processing completed"
    )

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_email_message(
        cls, email_msg: EmailMessage, correlation_id: str
    ) -> "VoicemailMessage":
        """Create VoicemailMessage from email.message.EmailMessage."""
        # Extract basic email information
        message_id = email_msg.get("Message-ID", "")
        sender = email_msg.get("From", "")
        recipients = []

        # Parse recipients from To, Cc, Bcc headers
        for header in ["To", "Cc", "Bcc"]:
            value = email_msg.get(header)
            if value:
                # Simple parsing - in production, use email.utils.getaddresses
                recipients.extend([addr.strip() for addr in value.split(",")])

        subject = email_msg.get("Subject", "")

        # Extract headers
        headers = dict(email_msg.items())

        # Extract body content
        body_text = None
        body_html = None

        if email_msg.is_multipart():
            for part in email_msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" and not body_text:
                    body_text = part.get_content()
                elif content_type == "text/html" and not body_html:
                    body_html = part.get_content()
        else:
            content_type = email_msg.get_content_type()
            content = email_msg.get_content()
            if content_type == "text/plain":
                body_text = content
            elif content_type == "text/html":
                body_html = content

        # Extract attachments
        audio_attachments = []
        other_attachments = []

        if email_msg.is_multipart():
            for part in email_msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" in content_disposition:
                    filename = part.get_filename() or "unknown"
                    content_type = part.get_content_type()
                    data = part.get_content()

                    if isinstance(data, str):
                        data = data.encode()

                    if content_type.startswith("audio/"):
                        audio_attachments.append(
                            AudioAttachment(
                                filename=filename,
                                content_type=content_type,
                                size_bytes=len(data),
                                data=data,
                            )
                        )
                    else:
                        other_attachments.append(
                            {
                                "filename": filename,
                                "content_type": content_type,
                                "size_bytes": len(data),
                                "data": data,
                            }
                        )

        return cls(
            correlation_id=correlation_id,
            message_id=message_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            headers=headers,
            audio_attachments=audio_attachments,
            other_attachments=other_attachments,
        )

    def has_audio_attachments(self) -> bool:
        """Check if message has any audio attachments."""
        return len(self.audio_attachments) > 0

    def get_total_audio_size(self) -> int:
        """Get total size of all audio attachments in bytes."""
        return sum(attachment.size_bytes for attachment in self.audio_attachments)


class ProcessingResult(BaseModel):
    """Result of processing a voicemail message."""

    correlation_id: str = Field(..., description="Correlation ID from original message")
    success: bool = Field(..., description="Whether processing was successful")
    transcriptions_count: int = Field(
        default=0, description="Number of successful transcriptions"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    processing_time_ms: int = Field(
        ..., description="Total processing time in milliseconds"
    )
    forwarded: bool = Field(default=False, description="Whether email was forwarded")
    files_cleaned: bool = Field(
        default=False, description="Whether temporary files were cleaned"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "correlation_id": "req_123456789",
                "success": True,
                "transcriptions_count": 1,
                "error_message": None,
                "processing_time_ms": 2500,
                "forwarded": True,
                "files_cleaned": True,
            }
        }
    }
