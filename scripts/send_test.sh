#!/bin/bash

# SMTP Voicemail Proxy - Test Email Sender
# Easy-to-use shell script wrapper for send_test_email.py

set -e  # Exit on any error

# Default values
SMTP_HOST="localhost"
SMTP_PORT="1025"
FROM_EMAIL="voicemail-proxy@broomfield.org"
TO_EMAIL="akasianov@broomfield.org"
COUNT=1
WAV_FILES=("./scripts/VoiceMsg.wav")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
SMTP Voicemail Proxy - Test Email Sender

Usage: $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -H, --host HOST         SMTP server host (default: localhost)
    -p, --port PORT         SMTP server port (default: 1025)
    -f, --from EMAIL        From email address (default: avaya-system@company.com)
    -t, --to EMAIL          To email address (default: user@company.com)
    -w, --wav FILE          WAV file to attach (can be used multiple times)
    -c, --count NUMBER      Number of test emails to send (default: 1)
    -s, --sample            Use sample WAV data instead of files
    -v, --verbose           Verbose output

EXAMPLES:
    # Send basic test email with sample data
    $0

    # Send with custom email addresses
    $0 --from avaya@company.com --to recipient@company.com

    # Send with actual WAV files
    $0 --wav voicemail1.wav --wav voicemail2.wav --to user@company.com

    # Send multiple test emails
    $0 --count 3 --from avaya@company.com --to user@company.com

    # Send to different SMTP server
    $0 --host mail.company.com --port 587 --from avaya@company.com --to user@company.com

    # Send with multiple WAV files
    $0 --wav /path/to/voicemail1.wav --wav /path/to/voicemail2.wav
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -H|--host)
            SMTP_HOST="$2"
            shift 2
            ;;
        -p|--port)
            SMTP_PORT="$2"
            shift 2
            ;;
        -f|--from)
            FROM_EMAIL="$2"
            shift 2
            ;;
        -t|--to)
            TO_EMAIL="$2"
            shift 2
            ;;
        -w|--wav)
            WAV_FILES+=("$2")
            shift 2
            ;;
        -c|--count)
            COUNT="$2"
            shift 2
            ;;
        -s|--sample)
            WAV_FILES=()  # Clear any WAV files to use sample data
            shift
            ;;
        -v|--verbose)
            set -x  # Enable verbose mode
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/send_test_email.py"

# Check if Python script exists
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    print_error "Python script not found: $PYTHON_SCRIPT"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

# Validate email addresses
validate_email() {
    local email="$1"
    if [[ ! "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        print_error "Invalid email address: $email"
        exit 1
    fi
}

validate_email "$FROM_EMAIL"
validate_email "$TO_EMAIL"

# Validate port number
if [[ ! "$SMTP_PORT" =~ ^[0-9]+$ ]] || [[ "$SMTP_PORT" -lt 1 ]] || [[ "$SMTP_PORT" -gt 65535 ]]; then
    print_error "Invalid port number: $SMTP_PORT"
    exit 1
fi

# Validate count
if [[ ! "$COUNT" =~ ^[0-9]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
    print_error "Invalid count: $COUNT"
    exit 1
fi

# Check WAV files if provided
if [[ ${#WAV_FILES[@]} -gt 0 ]]; then
    for wav_file in "${WAV_FILES[@]}"; do
        if [[ ! -f "$wav_file" ]]; then
            print_error "WAV file not found: $wav_file"
            exit 1
        fi
        if [[ ! "$wav_file" =~ \.(wav|WAV)$ ]]; then
            print_warning "File may not be a WAV file: $wav_file"
        fi
    done
fi

# Display configuration
print_info "SMTP Voicemail Proxy Test Email Sender"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SMTP Server: $SMTP_HOST:$SMTP_PORT"
echo "From:        $FROM_EMAIL"
echo "To:          $TO_EMAIL"
echo "Count:       $COUNT"

if [[ ${#WAV_FILES[@]} -gt 0 ]]; then
    echo "WAV Files:   ${WAV_FILES[*]}"
else
    echo "WAV Files:   Using sample data"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Build Python command
PYTHON_CMD=(python3 "$PYTHON_SCRIPT" --host "$SMTP_HOST" --port "$SMTP_PORT" --from "$FROM_EMAIL" --to "$TO_EMAIL" --count "$COUNT")

# Add WAV files if provided
if [[ ${#WAV_FILES[@]} -gt 0 ]]; then
    PYTHON_CMD+=(--wav-files "${WAV_FILES[@]}")
fi

# Execute the Python script
print_info "Executing: ${PYTHON_CMD[*]}"
echo

if "${PYTHON_CMD[@]}"; then
    print_success "Test email(s) sent successfully!"
    exit 0
else
    print_error "Failed to send test email(s)"
    exit 1
fi