#!/usr/bin/env python3
"""
Test script to send sample voicemail emails to the SMTP proxy.
"""

import smtplib
import os
import argparse
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime


def create_sample_wav_data():
    """Create a minimal WAV file for testing."""
    # This creates a minimal valid WAV header with silence
    # In production, you'd use real audio files
    wav_header = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x00\x00"
    return wav_header


def load_wav_file(file_path):
    """Load WAV file from disk."""
    try:
        with open(file_path, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"✗ Error loading WAV file {file_path}: {e}")
        return None


def send_test_email(
    from_email="avaya-system@company.com",
    to_email="user@company.com",
    wav_files=None,
    smtp_host="localhost",
    smtp_port=1025,
):
    """Send a test voicemail email."""

    if wav_files is None:
        wav_files = []

    # Extract caller info from first WAV file name or use defaults
    caller_name = "John Doe"
    caller_phone = "555-1234"
    duration = 45

    if wav_files:
        # Try to extract info from filename
        first_file = Path(wav_files[0])
        filename = first_file.stem
        # You could add logic here to parse caller info from filename

    # Create message
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = f"Voicemail from {caller_name} ({caller_phone})"
    msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

    # Add Avaya-style headers
    msg["X-Avaya-System"] = "IP Office"
    msg["X-Voicemail-Duration"] = str(duration)
    msg["X-Caller-ID"] = caller_phone
    msg["X-Caller-Name"] = caller_name

    # Add body text
    body_text = f"""
You have received a new voicemail message.

Caller: {caller_name}
Phone: {caller_phone}
Duration: {duration} seconds
Received: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Please check the attached audio file(s).

Best regards,
Avaya IP Office System
    """

    text_part = MIMEText(body_text, "plain")
    msg.attach(text_part)

    # Add HTML version
    html_body = f"""
    <html>
    <body>
        <h2>New Voicemail Message</h2>
        <table border="1" cellpadding="5">
            <tr><td><strong>Caller:</strong></td><td>{caller_name}</td></tr>
            <tr><td><strong>Phone:</strong></td><td>{caller_phone}</td></tr>
            <tr><td><strong>Duration:</strong></td><td>{duration} seconds</td></tr>
            <tr><td><strong>Received:</strong></td><td>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
        </table>
        <p>Please check the attached audio file(s).</p>
        <hr>
        <p><em>Avaya IP Office System</em></p>
    </body>
    </html>
    """

    html_part = MIMEText(html_body, "html")
    msg.attach(html_part)

    # Add WAV attachments
    if wav_files:
        for wav_file in wav_files:
            wav_path = Path(wav_file)
            if not wav_path.exists():
                print(f"✗ WAV file not found: {wav_file}")
                continue

            wav_data = load_wav_file(wav_file)
            if wav_data is None:
                continue

            # Determine the correct MIME type based on file extension
            if wav_path.suffix.lower() == ".mp3":
                audio_part = MIMEApplication(wav_data, _subtype="mpeg")
                audio_part.set_type("audio/mpeg")
            elif wav_path.suffix.lower() == ".wav":
                audio_part = MIMEApplication(wav_data, _subtype="wav")
                audio_part.set_type("audio/wav")
            else:
                # Default to audio/wav for unknown audio files
                audio_part = MIMEApplication(wav_data, _subtype="wav")
                audio_part.set_type("audio/wav")

            audio_part.add_header(
                "Content-Disposition", "attachment", filename=wav_path.name
            )
            msg.attach(audio_part)
            print(f"  ✓ Attached: {wav_path.name} ({len(wav_data)} bytes)")
    else:
        # Use sample WAV data if no files provided
        wav_data = create_sample_wav_data()
        audio_part = MIMEApplication(wav_data, _subtype="wav")
        audio_part.set_type("audio/wav")
        audio_part.add_header(
            "Content-Disposition", "attachment", filename="sample_voicemail.wav"
        )
        msg.attach(audio_part)
        print(
            f"  ✓ Attached: sample_voicemail.wav ({len(wav_data)} bytes - sample data)"
        )

    # Send email
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.send_message(msg)
            print(f"✓ Test email sent successfully to {smtp_host}:{smtp_port}")
            print(f"  From: {msg['From']}")
            print(f"  To: {msg['To']}")
            print(f"  Subject: {msg['Subject']}")

    except Exception as e:
        print(f"✗ Failed to send test email: {e}")
        return False

    return True


def send_multiple_test_emails(
    count=3,
    from_email="avaya-system@company.com",
    to_email="user@company.com",
    wav_files=None,
    smtp_host="localhost",
    smtp_port=1025,
):
    """Send multiple test emails with different scenarios."""

    successful = 0

    for i in range(count):
        print(f"\nSending test email {i+1}/{count}...")

        # Use different recipient for each email if sending multiple
        current_to = to_email
        if count > 1:
            # Add number to email address
            email_parts = to_email.split("@")
            if len(email_parts) == 2:
                current_to = f"{email_parts[0]}{i+1}@{email_parts[1]}"

        # Send individual email
        success = send_test_email(
            from_email=from_email,
            to_email=current_to,
            wav_files=wav_files,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
        )

        if success:
            print(f"  ✓ Sent to {current_to}")
            successful += 1
        else:
            print(f"  ✗ Failed to send to {current_to}")

    print(f"\nSent {successful}/{count} test emails successfully")
    return successful == count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Send test voicemail emails to SMTP proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send with sample WAV data
  python send_test_email.py --from avaya@company.com --to user@company.com

  # Send with actual WAV files
  python send_test_email.py --from avaya@company.com --to user@company.com --wav-files voicemail1.wav voicemail2.wav

  # Send multiple test emails
  python send_test_email.py --from avaya@company.com --to user@company.com --count 3

  # Use different SMTP server
  python send_test_email.py --host mail.company.com --port 587 --from avaya@company.com --to user@company.com
        """,
    )

    # Email settings
    parser.add_argument(
        "--from",
        dest="from_email",
        default="avaya-system@company.com",
        help="From email address (default: avaya-system@company.com)",
    )
    parser.add_argument(
        "--to",
        dest="to_email",
        default="user@company.com",
        help="To email address (default: user@company.com)",
    )

    # WAV file settings
    parser.add_argument(
        "--wav-files",
        nargs="*",
        help="Path(s) to WAV file(s) to attach. If not provided, uses sample data.",
    )

    # SMTP settings
    parser.add_argument(
        "--host", default="localhost", help="SMTP host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=1025, help="SMTP port (default: 1025)"
    )

    # Testing options
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of test emails to send (default: 1)",
    )

    args = parser.parse_args()

    print(f"Sending test emails to {args.host}:{args.port}")
    print(f"From: {args.from_email}")
    print(f"To: {args.to_email}")

    if args.wav_files:
        print(f"WAV files: {', '.join(args.wav_files)}")
        # Verify files exist
        missing_files = [f for f in args.wav_files if not Path(f).exists()]
        if missing_files:
            print(f"✗ Missing WAV files: {', '.join(missing_files)}")
            exit(1)
    else:
        print("Using sample WAV data")

    print()

    if args.count == 1:
        success = send_test_email(
            from_email=args.from_email,
            to_email=args.to_email,
            wav_files=args.wav_files,
            smtp_host=args.host,
            smtp_port=args.port,
        )
        exit(0 if success else 1)
    else:
        success = send_multiple_test_emails(
            count=args.count,
            from_email=args.from_email,
            to_email=args.to_email,
            wav_files=args.wav_files,
            smtp_host=args.host,
            smtp_port=args.port,
        )
        exit(0 if success else 1)
