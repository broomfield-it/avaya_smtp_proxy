"""Email processing and enhancement service."""

import smtplib
import ssl
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formataddr, parseaddr
from typing import List, Optional, Dict, Any
import asyncio

from ..models.config import OutboundSMTPConfig
from ..models.messages import VoicemailMessage, TranscriptionResult
from ..utils.logging import LoggerMixin


class EmailProcessor(LoggerMixin):
    """Service for processing and forwarding enhanced emails."""

    def __init__(self, config: OutboundSMTPConfig):
        self.config = config

    async def enhance_and_forward(
        self,
        voicemail_msg: VoicemailMessage,
        transcription_results: List[Optional[TranscriptionResult]],
    ) -> bool:
        """
        Enhance email with transcriptions and forward to recipients.

        Args:
            voicemail_msg: Original voicemail message
            transcription_results: List of transcription results (can contain None)

        Returns:
            True if forwarding was successful, False otherwise
        """
        try:
            # Create enhanced email
            enhanced_email = await self._create_enhanced_email(
                voicemail_msg, transcription_results
            )

            if not enhanced_email:
                self.log_error("Failed to create enhanced email")
                return False

            # Send the enhanced email
            success = await self._send_email(enhanced_email, voicemail_msg.recipients)

            if success:
                self.log_info(
                    f"Successfully forwarded enhanced email",
                    recipients_count=len(voicemail_msg.recipients),
                    transcriptions_count=len(
                        [r for r in transcription_results if r is not None]
                    ),
                )
            else:
                self.log_error("Failed to send enhanced email")

            return success

        except Exception as e:
            self.log_error(f"Error in enhance_and_forward: {e}")
            return False

    async def _create_enhanced_email(
        self,
        voicemail_msg: VoicemailMessage,
        transcription_results: List[Optional[TranscriptionResult]],
    ) -> Optional[EmailMessage]:
        """
        Create enhanced email with transcriptions.

        Args:
            voicemail_msg: Original voicemail message
            transcription_results: List of transcription results

        Returns:
            Enhanced EmailMessage or None if creation failed
        """
        try:
            # Create multipart message
            msg = MIMEMultipart("alternative")

            # Copy original headers (excluding some that should be regenerated)
            skip_headers = {
                "message-id",
                "date",
                "from",
                "to",
                "cc",
                "bcc",
                "subject",
                "content-type",
                "content-transfer-encoding",
                "mime-version",
            }

            for header, value in voicemail_msg.headers.items():
                if header.lower() not in skip_headers:
                    msg[header] = value

            # Set basic email headers
            msg["From"] = voicemail_msg.sender
            msg["To"] = ", ".join(voicemail_msg.recipients)
            msg["Subject"] = self._enhance_subject(
                voicemail_msg.subject, transcription_results
            )

            # Add transcription enhancement indicator
            msg["X-Transcription-Enhanced"] = "true"
            msg["X-Correlation-ID"] = voicemail_msg.correlation_id

            # Create enhanced body content
            plain_text_body = self._create_plain_text_body(
                voicemail_msg, transcription_results
            )
            html_body = self._create_html_body(voicemail_msg, transcription_results)

            # Add text parts
            if plain_text_body:
                text_part = MIMEText(plain_text_body, "plain", "utf-8")
                msg.attach(text_part)

            if html_body:
                html_part = MIMEText(html_body, "html", "utf-8")
                msg.attach(html_part)

            # Add original attachments (including audio files)
            await self._add_attachments(msg, voicemail_msg)

            return msg

        except Exception as e:
            self.log_error(f"Failed to create enhanced email: {e}")
            return None

    def _enhance_subject(
        self,
        original_subject: str,
        transcription_results: List[Optional[TranscriptionResult]],
    ) -> str:
        """
        Enhance email subject with transcription indicator.

        Args:
            original_subject: Original email subject
            transcription_results: List of transcription results

        Returns:
            Enhanced subject line
        """
        successful_transcriptions = [r for r in transcription_results if r is not None]

        if successful_transcriptions:
            # Add transcription indicator to subject
            if not original_subject.startswith("[Transcribed]"):
                return f"[Transcribed] {original_subject}"
        else:
            # Add failed transcription indicator
            if not original_subject.startswith("[Audio]"):
                return f"[Audio] {original_subject}"

        return original_subject

    def _create_plain_text_body(
        self,
        voicemail_msg: VoicemailMessage,
        transcription_results: List[Optional[TranscriptionResult]],
    ) -> str:
        """
        Create enhanced plain text email body.

        Args:
            voicemail_msg: Original voicemail message
            transcription_results: List of transcription results

        Returns:
            Enhanced plain text body
        """
        lines = []

        # Add transcription header
        successful_transcriptions = [r for r in transcription_results if r is not None]

        if successful_transcriptions:
            lines.append("=== VOICEMAIL TRANSCRIPTION ===")
            lines.append("")

            for i, result in enumerate(successful_transcriptions):
                if len(successful_transcriptions) > 1:
                    lines.append(f"Audio File {i+1}:")

                lines.append(f"Transcript: {result.transcript}")
                lines.append(f"Confidence: {result.confidence:.2%}")

                if result.alternatives:
                    lines.append("Alternative transcriptions:")
                    for j, alt in enumerate(
                        result.alternatives[:3]
                    ):  # Show max 3 alternatives
                        lines.append(f"  {j+1}. {alt}")

                lines.append("")

            lines.append("=== END TRANSCRIPTION ===")
            lines.append("")
        else:
            if voicemail_msg.has_audio_attachments():
                lines.append("=== VOICEMAIL AUDIO ATTACHED ===")
                lines.append("(Transcription was not available for this message)")
                lines.append("")

        # Add original email body if present
        if voicemail_msg.body_text:
            lines.append("=== ORIGINAL MESSAGE ===")
            lines.append("")
            lines.append(voicemail_msg.body_text)

        return "\n".join(lines)

    def _create_html_body(
        self,
        voicemail_msg: VoicemailMessage,
        transcription_results: List[Optional[TranscriptionResult]],
    ) -> str:
        """
        Create enhanced HTML email body.

        Args:
            voicemail_msg: Original voicemail message
            transcription_results: List of transcription results

        Returns:
            Enhanced HTML body
        """
        html_parts = []

        html_parts.append("<!DOCTYPE html>")
        html_parts.append('<html><head><meta charset="utf-8"></head><body>')

        # Add transcription section
        successful_transcriptions = [r for r in transcription_results if r is not None]

        if successful_transcriptions:
            html_parts.append(
                '<div style="background-color: #f0f8ff; padding: 15px; border-left: 4px solid #007acc; margin-bottom: 20px;">'
            )
            html_parts.append(
                '<h3 style="color: #007acc; margin-top: 0;">🎤 Voicemail Transcription</h3>'
            )

            for i, result in enumerate(successful_transcriptions):
                if len(successful_transcriptions) > 1:
                    html_parts.append(f"<h4>Audio File {i+1}:</h4>")

                html_parts.append(
                    f"<p><strong>Transcript:</strong> {self._html_escape(result.transcript)}</p>"
                )
                html_parts.append(
                    f"<p><strong>Confidence:</strong> {result.confidence:.2%}</p>"
                )

                if result.alternatives:
                    html_parts.append(
                        "<p><strong>Alternative transcriptions:</strong></p>"
                    )
                    html_parts.append("<ul>")
                    for alt in result.alternatives[:3]:  # Show max 3 alternatives
                        html_parts.append(f"<li>{self._html_escape(alt)}</li>")
                    html_parts.append("</ul>")

                if i < len(successful_transcriptions) - 1:
                    html_parts.append("<hr>")

            html_parts.append("</div>")
        else:
            if voicemail_msg.has_audio_attachments():
                html_parts.append(
                    '<div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin-bottom: 20px;">'
                )
                html_parts.append(
                    '<h3 style="color: #856404; margin-top: 0;">🔊 Voicemail Audio Attached</h3>'
                )
                html_parts.append(
                    "<p>Transcription was not available for this message. Please check the attached audio file.</p>"
                )
                html_parts.append("</div>")

        # Add original email body if present
        if voicemail_msg.body_html or voicemail_msg.body_text:
            html_parts.append(
                '<div style="border-top: 1px solid #ccc; padding-top: 20px;">'
            )
            html_parts.append("<h3>Original Message</h3>")

            if voicemail_msg.body_html:
                # Include original HTML (with some safety considerations)
                html_parts.append(voicemail_msg.body_html)
            elif voicemail_msg.body_text:
                # Convert plain text to HTML
                escaped_text = self._html_escape(voicemail_msg.body_text)
                formatted_text = escaped_text.replace("\n", "<br>")
                html_parts.append(
                    f'<div style="white-space: pre-wrap;">{formatted_text}</div>'
                )

            html_parts.append("</div>")

        html_parts.append("</body></html>")

        return "\n".join(html_parts)

    def _html_escape(self, text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    async def _add_attachments(
        self, msg: MIMEMultipart, voicemail_msg: VoicemailMessage
    ) -> None:
        """
        Add original attachments to the enhanced email.

        Args:
            msg: Email message to add attachments to
            voicemail_msg: Original voicemail message with attachments
        """
        try:
            # Add audio attachments
            for attachment in voicemail_msg.audio_attachments:
                audio_part = MIMEApplication(
                    attachment.data, _subtype=attachment.content_type.split("/")[-1]
                )
                audio_part.add_header(
                    "Content-Disposition", "attachment", filename=attachment.filename
                )
                msg.attach(audio_part)

            # Add other attachments
            for attachment in voicemail_msg.other_attachments:
                other_part = MIMEApplication(
                    attachment["data"],
                    _subtype=attachment["content_type"].split("/")[-1],
                )
                other_part.add_header(
                    "Content-Disposition", "attachment", filename=attachment["filename"]
                )
                msg.attach(other_part)

        except Exception as e:
            self.log_error(f"Failed to add attachments: {e}")

    async def _send_email(self, email_msg: EmailMessage, recipients: List[str]) -> bool:
        """
        Send email via SMTP.

        Args:
            email_msg: Email message to send
            recipients: List of recipient email addresses

        Returns:
            True if sending was successful, False otherwise
        """
        try:
            # Run SMTP operations in executor since they're blocking
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._send_email_sync, email_msg, recipients
            )

            if result:
                self.log_info(
                    f"Email sent successfully via SMTP to {len(recipients)} recipients"
                )

            return result

        except Exception as e:
            self.log_error(
                f"Failed to send email: {e} (host: {self.config.host}:{self.config.port}, type: {type(e).__name__})"
            )
            return False

    def _send_email_sync(self, email_msg: EmailMessage, recipients: List[str]) -> bool:
        """
        Synchronous email sending operation.

        Args:
            email_msg: Email message to send
            recipients: List of recipient email addresses

        Returns:
            True if sending was successful, False otherwise
        """
        smtp_client = None
        try:
            # Create SMTP connection
            smtp_client = self._create_smtp_client_sync()

            if not smtp_client:
                return False

            # Send the email
            smtp_client.send_message(email_msg, to_addrs=recipients)

            return True

        except Exception as e:
            self.log_error(f"Sync email send failed: {e}")
            return False

        finally:
            if smtp_client:
                try:
                    smtp_client.quit()
                except:
                    pass  # Ignore cleanup errors

    def _create_smtp_client_sync(self) -> Optional[smtplib.SMTP]:
        """
        Create and configure SMTP client synchronously.

        Returns:
            Configured SMTP client or None if creation failed
        """
        try:
            # Create SMTP client
            if self.config.use_ssl:
                # Use SMTP_SSL for port 465
                context = ssl.create_default_context()
                smtp_client = smtplib.SMTP_SSL(
                    self.config.host,
                    self.config.port,
                    context=context,
                    timeout=self.config.timeout,
                )
            else:
                # Use regular SMTP
                smtp_client = smtplib.SMTP(
                    self.config.host, self.config.port, timeout=self.config.timeout
                )

                # Use STARTTLS if configured
                if self.config.use_tls:
                    context = ssl.create_default_context()
                    smtp_client.starttls(context=context)

            # Authenticate if credentials provided
            if self.config.user and self.config.password:
                smtp_client.login(self.config.user, self.config.password)

                self.log_debug(
                    f"SMTP authentication successful for {self.config.user}@{self.config.host}"
                )

            return smtp_client

        except Exception as e:
            self.log_error(
                f"Failed to create SMTP client: {e} (host: {self.config.host}:{self.config.port}, type: {type(e).__name__})"
            )
            return None
