#!/bin/bash

# Example usage of the SMTP Voicemail Proxy test email sender

echo "SMTP Voicemail Proxy - Example Usage"
echo "====================================="
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "1. Basic test with sample WAV data:"
echo "   $SCRIPT_DIR/send_test.sh"
echo

echo "2. Test with custom email addresses:"
echo "   $SCRIPT_DIR/send_test.sh --from avaya@company.com --to recipient@company.com"
echo

echo "3. Test with actual WAV files:"
echo "   $SCRIPT_DIR/send_test.sh --wav /path/to/voicemail1.wav --wav /path/to/voicemail2.wav --to user@company.com"
echo

echo "4. Send multiple test emails:"
echo "   $SCRIPT_DIR/send_test.sh --count 3 --from avaya@company.com --to user@company.com"
echo

echo "5. Test with different SMTP server:"
echo "   $SCRIPT_DIR/send_test.sh --host mail.company.com --port 587 --from avaya@company.com --to user@company.com"
echo

echo "6. Python script direct usage:"
echo "   python3 $SCRIPT_DIR/send_test_email.py --help"
echo

echo "Available options:"
echo "  -h, --help              Show help message"
echo "  -H, --host HOST         SMTP server host"
echo "  -p, --port PORT         SMTP server port"
echo "  -f, --from EMAIL        From email address"
echo "  -t, --to EMAIL          To email address"
echo "  -w, --wav FILE          WAV file to attach (can be used multiple times)"
echo "  -c, --count NUMBER      Number of test emails"
echo "  -s, --sample            Use sample WAV data"
echo "  -v, --verbose           Verbose output"
echo

# Check if we have any sample WAV files
echo "Looking for sample WAV files..."
if find . -name "*.wav" -type f 2>/dev/null | head -5; then
    echo
    echo "Found WAV files! You can use them like:"
    echo "   $SCRIPT_DIR/send_test.sh --wav \"\$(find . -name '*.wav' -type f | head -1)\" --to user@company.com"
else
    echo "No WAV files found in current directory."
    echo "The script will use sample WAV data by default."
fi
echo

echo "To run a quick test:"
echo "   $SCRIPT_DIR/send_test.sh --to your-email@company.com"