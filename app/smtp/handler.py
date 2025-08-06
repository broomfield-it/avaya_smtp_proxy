"""SMTP message handler for processing incoming emails."""

import asyncio
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from typing import Optional

from aiosmtpd.smtp import Envelope, Session, SMTP as SMTPProtocol

from ..models.config import AppConfig
from ..models.messages import VoicemailMessage
from ..utils.correlation import generate_correlation_id, set_correlation_id
from ..utils.logging import LoggerMixin
from ..tasks.email_tasks import process_voicemail_email


class SMTPHandler(LoggerMixin):
    """Async SMTP handler for processing incoming voicemail emails."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.parser = BytesParser(policy=default)

    async def handle_RCPT(
        self,
        server: SMTPProtocol,
        session: Session,
        envelope: Envelope,
        address: str,
        rcpt_options: list,
    ) -> str:
        """Handle RCPT TO command."""
        # Generate correlation ID for this email session
        if not hasattr(session, "correlation_id"):
            session.correlation_id = generate_correlation_id()
            set_correlation_id(session.correlation_id)

        self.log_info(
            f"Accepting recipient: {address}",
            recipient=address,
            sender=envelope.mail_from,
        )

        # Accept all recipients (we'll validate later if needed)
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(
        self, server: SMTPProtocol, session: Session, envelope: Envelope
    ) -> str:
        """Handle email data and queue for processing."""
        # Set correlation ID from session
        correlation_id = getattr(session, "correlation_id", generate_correlation_id())
        set_correlation_id(correlation_id)

        try:
            # Parse the email message
            email_message = self.parser.parsebytes(envelope.content)

            # Create VoicemailMessage object
            voicemail_msg = VoicemailMessage.from_email_message(
                email_message, correlation_id
            )

            self.log_info(
                f"Received email from {voicemail_msg.sender} to {len(voicemail_msg.recipients)} recipients",
                sender=voicemail_msg.sender,
                recipients_count=len(voicemail_msg.recipients),
                subject=voicemail_msg.subject,
                has_audio=voicemail_msg.has_audio_attachments(),
                audio_count=len(voicemail_msg.audio_attachments),
                total_audio_size=voicemail_msg.get_total_audio_size(),
            )

            # Validate message
            if not voicemail_msg.has_audio_attachments():
                self.log_warning("Email has no audio attachments, processing anyway")

            # Check audio size limits
            total_audio_size = voicemail_msg.get_total_audio_size()
            max_size = self.config.storage.max_audio_size_bytes

            if total_audio_size > max_size:
                self.log_error(
                    f"Audio attachments too large: {total_audio_size} bytes (max: {max_size})",
                    total_size=total_audio_size,
                    max_size=max_size,
                )
                return "552 Message size exceeds maximum allowed"

            # Queue the message for async processing
            task = process_voicemail_email.delay(voicemail_msg.dict())

            self.log_info(
                f"Queued email for processing", task_id=task.id, queue_name="default"
            )

            return "250 Message accepted for delivery"

        except Exception as e:
            self.log_error(
                f"Failed to process incoming email: {e}",
                error_type=type(e).__name__,
                sender=envelope.mail_from,
                recipients=envelope.rcpt_tos,
            )

            # Return temporary failure to allow retry
            return "451 Requested action aborted: local error in processing"

    async def handle_MAIL(
        self,
        server: SMTPProtocol,
        session: Session,
        envelope: Envelope,
        address: str,
        mail_options: list,
    ) -> str:
        """Handle MAIL FROM command."""
        # Generate correlation ID for new email session
        correlation_id = generate_correlation_id()
        session.correlation_id = correlation_id
        set_correlation_id(correlation_id)

        self.log_info(
            f"New email session started",
            sender=address,
            client_addr=session.peer[0] if session.peer else "unknown",
        )

        envelope.mail_from = address
        return "250 OK"

    async def handle_RSET(
        self, server: SMTPProtocol, session: Session, envelope: Envelope
    ) -> str:
        """Handle RSET command."""
        if hasattr(session, "correlation_id"):
            set_correlation_id(session.correlation_id)
            self.log_debug("SMTP session reset")

        return "250 OK"

    async def handle_QUIT(
        self, server: SMTPProtocol, session: Session, envelope: Envelope
    ) -> str:
        """Handle QUIT command."""
        if hasattr(session, "correlation_id"):
            set_correlation_id(session.correlation_id)
            self.log_debug("SMTP session ended")

        return "221 Goodbye"

    async def handle_exception(self, error: Exception) -> str:
        """Handle unhandled exceptions in SMTP processing."""
        correlation_id = generate_correlation_id()
        set_correlation_id(correlation_id)

        self.log_error(
            f"Unhandled SMTP exception: {error}",
            error_type=type(error).__name__,
            exception=str(error),
        )

        return "451 Requested action aborted: local error in processing"
