# SMTP Voicemail Proxy with Speech Transcription

A production-ready SMTP proxy service that intercepts Avaya voicemail notifications, transcribes attached WAV files using Google Speech-to-Text API, and forwards enhanced emails with transcriptions to users.

## Features

- **Async SMTP Server**: High-performance email reception with `aiosmtpd`
- **Speech Transcription**: Google Cloud Speech-to-Text integration
- **Email Enhancement**: Adds transcriptions to email body (plain text and HTML)
- **Scalable Processing**: Celery-based async task queue with Redis
- **Container Ready**: Full Docker and Docker Compose support
- **Production Monitoring**: Health checks, metrics, and observability
- **Secure**: TLS/SSL support, non-root containers, secret management

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose
- Google Cloud Platform account with Speech-to-Text API enabled
- SMTP server for forwarding emails (e.g., Office 365, Gmail, corporate mail server)

### 2. Setup

1. **Clone and configure:**
   ```bash
   git clone <repository-url>
   cd avaya_smtp_proxy
   cp .env.example .env
   ```

2. **Configure environment variables** in `.env`:
   ```bash
   # Required: Outbound SMTP for forwarding
   OUTBOUND_SMTP_HOST=mail.your-company.com
   OUTBOUND_SMTP_USER=voicemail-proxy@your-company.com
   OUTBOUND_SMTP_PASSWORD=your-password
   
   # Required: Google Cloud
   GOOGLE_PROJECT_ID=your-gcp-project-id
   ```

3. **Add Google service account credentials:**
   ```bash
   mkdir credentials
   # Copy your service-account.json file to credentials/
   ```

4. **Start services:**
   ```bash
   make up
   # or
   docker-compose up -d
   ```

### 3. Configure Avaya

Configure your Avaya system to send voicemail notifications to:
- **SMTP Server**: `<your-server-ip>`
- **Port**: `1025` (or your configured port)
- **Authentication**: None (unless configured)

### 4. Test

Send a test email:
```bash
python scripts/send_test_email.py --host localhost --port 1025
```

Check logs:
```bash
make logs
```

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│    Avaya    │───▶│ SMTP Proxy   │───▶│   Redis     │
│   System    │    │   Server     │    │   Queue     │
└─────────────┘    └──────────────┘    └─────────────┘
                           │                    │
                           ▼                    ▼
                   ┌──────────────┐    ┌─────────────┐
                   │    Health    │    │   Celery    │
                   │   Monitor    │    │   Worker    │
                   └──────────────┘    └─────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
                  │   Google    │    │    Email    │    │    File     │
                  │   Speech    │    │  Processor  │    │  Manager    │
                  │     API     │    │             │    │             │
                  └─────────────┘    └─────────────┘    └─────────────┘
                                              │
                                              ▼
                                     ┌─────────────┐
                                     │  Enhanced   │
                                     │    Email    │
                                     │ Forwarding  │
                                     └─────────────┘
```

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OUTBOUND_SMTP_HOST` | Outbound SMTP server | `mail.company.com` |
| `OUTBOUND_SMTP_USER` | SMTP username | `proxy@company.com` |
| `OUTBOUND_SMTP_PASSWORD` | SMTP password | `secure-password` |
| `GOOGLE_PROJECT_ID` | Google Cloud project ID | `my-project-123` |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_PORT` | `1025` | Incoming SMTP port |
| `SMTP_AUTH_REQUIRED` | `false` | Require SMTP auth |
| `GOOGLE_LANGUAGE_CODE` | `en-US` | Speech recognition language |
| `CELERY_WORKER_CONCURRENCY` | `4` | Worker processes |
| `LOG_LEVEL` | `INFO` | Logging level |

See `.env.example` for complete configuration options.

## Deployment

### Production Deployment

1. **Security Configuration:**
   ```bash
   # Enable TLS for SMTP
   SMTP_TLS_CERT=/app/certs/smtp.crt
   SMTP_TLS_KEY=/app/certs/smtp.key
   
   # Strong authentication
   SMTP_AUTH_REQUIRED=true
   SMTP_AUTH_USER=avaya
   SMTP_AUTH_PASSWORD=strong-password
   ```

2. **Resource Limits:**
   ```bash
   # Worker scaling
   CELERY_WORKER_CONCURRENCY=8
   
   # Storage limits
   STORAGE_MAX_AUDIO_SIZE_MB=100
   STORAGE_CLEANUP_AFTER_HOURS=48
   ```

3. **Monitoring:**
   ```bash
   # Enable monitoring stack
   docker-compose --profile monitoring up -d
   ```

### Kubernetes Deployment

Example Kubernetes manifests available in `k8s/` directory:
- ConfigMap for configuration
- Deployment for SMTP proxy
- Deployment for Celery workers
- Service and Ingress definitions
- PersistentVolumeClaim for storage

## Monitoring and Observability

### Health Checks

- **Health endpoint**: `http://localhost:8000/health`
- **Readiness check**: `http://localhost:8000/health/ready`
- **Metrics**: `http://localhost:8000/metrics` (Prometheus format)

### Monitoring Tools

1. **Flower** (Celery monitoring): `http://localhost:5555`
2. **Redis Insight**: `http://localhost:8001` (dev profile)
3. **Application logs**: `docker-compose logs -f`

### Key Metrics

- SMTP connection counts and duration
- Queue depths and processing times
- Google API response times and errors
- Email processing success/failure rates
- Storage usage and cleanup statistics

## Troubleshooting

### Common Issues

1. **Email not being processed:**
   ```bash
   # Check SMTP server logs
   make logs-smtp
   
   # Check worker logs
   make logs-worker
   
   # Verify Redis connectivity
   docker-compose exec redis redis-cli ping
   ```

2. **Transcription failures:**
   ```bash
   # Verify Google credentials
   docker-compose exec smtp-proxy ls -la /app/credentials/
   
   # Check Google API quota
   # Check logs for Google API errors
   make logs-worker | grep "Google"
   ```

3. **Email forwarding issues:**
   ```bash
   # Test SMTP connectivity
   docker-compose exec smtp-proxy python -c "
   import smtplib
   with smtplib.SMTP('$OUTBOUND_SMTP_HOST', $OUTBOUND_SMTP_PORT) as s:
       s.starttls()
       s.login('$OUTBOUND_SMTP_USER', '$OUTBOUND_SMTP_PASSWORD')
       print('SMTP OK')
   "
   ```

### Log Analysis

Logs are structured JSON for easy parsing:
```bash
# Filter by correlation ID
make logs | jq 'select(.correlation_id == "req_abc123")'

# Show only errors
make logs | jq 'select(.level == "ERROR")'

# Monitor transcription success rate
make logs | jq 'select(.message | contains("transcription completed"))'
```

### Performance Tuning

1. **Scale workers:**
   ```bash
   docker-compose up -d --scale celery-worker=3
   ```

2. **Adjust concurrency:**
   ```bash
   CELERY_WORKER_CONCURRENCY=8
   ```

3. **Monitor resource usage:**
   ```bash
   docker stats
   ```

## Development

### Local Development

1. **Start development environment:**
   ```bash
   make dev
   ```

2. **Run tests:**
   ```bash
   make test
   ```

3. **Code formatting:**
   ```bash
   make format
   make lint
   ```

### Testing

- **Unit tests**: Test individual components
- **Integration tests**: Test full email processing pipeline
- **Load tests**: Verify SMTP server performance
- **Mock data**: Sample Avaya email fixtures

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run `make lint` and `make test`
5. Submit a pull request

## Security Considerations

- **Secrets Management**: Use Docker secrets or external secret management
- **Network Security**: TLS encryption for all connections
- **Container Security**: Non-root user, minimal attack surface
- **Input Validation**: Sanitize all email inputs
- **File Handling**: Secure temporary file operations
- **API Security**: Validate SSL certificates, proper authentication

## License

[MIT License](LICENSE)

## Support

For issues and questions:
- Check the troubleshooting guide above
- Review logs for error messages
- Open an issue with detailed information including:
  - Environment configuration
  - Log excerpts
  - Steps to reproduce

---

**Production Ready**: This service is designed for enterprise voicemail processing with high reliability, scalability, and comprehensive monitoring.