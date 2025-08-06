# SMTP Voicemail Proxy - Architecture Overview

## System Architecture

The SMTP Voicemail Proxy is a distributed system designed to handle Avaya voicemail notifications, transcribe audio attachments, and forward enhanced emails. The architecture follows microservices principles with clear separation of concerns.

## High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Avaya       │───▶│   SMTP Proxy    │───▶│     Redis       │
│   IP Office     │    │    Server       │    │   Message       │
│                 │    │                 │    │    Broker       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │     Health      │    │     Celery      │
                       │   Monitoring    │    │    Workers      │
                       │                 │    │   (Scalable)    │
                       └─────────────────┘    └─────────────────┘
                                                       │
                        ┌──────────────────────────────┼──────────────────────────────┐
                        ▼                              ▼                              ▼
               ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────┐
               │     Google      │           │      Email      │           │      File       │
               │   Speech-to-    │           │   Enhancement   │           │   Management    │
               │     Text        │           │   & Forwarding  │           │   & Cleanup     │
               └─────────────────┘           └─────────────────┘           └─────────────────┘
                        │                              │                              │
                        └──────────────────────────────▼──────────────────────────────┘
                                              ┌─────────────────┐
                                              │   Enhanced      │
                                              │   Email to      │
                                              │   Recipients    │
                                              └─────────────────┘
```

## Core Components

### 1. SMTP Proxy Server (`app/smtp/`)

**Purpose**: Receives emails from Avaya systems and queues them for processing.

**Key Features**:
- Async SMTP server using `aiosmtpd`
- Quick acknowledgment to prevent Avaya timeouts
- Email parsing and validation
- Correlation ID generation for tracking
- TLS/SSL support for secure connections

**Files**:
- `handler.py` - SMTP message handling logic
- `server.py` - SMTP server implementation

### 2. Task Processing System (`app/tasks/`)

**Purpose**: Handles async processing of voicemail emails using Celery.

**Key Features**:
- Distributed task queue with Redis
- Retry logic with exponential backoff
- Task monitoring and health checks
- Graceful error handling and cleanup

**Files**:
- `worker.py` - Celery worker configuration
- `email_tasks.py` - Task definitions for email processing

### 3. Transcription Service (`app/services/transcription.py`)

**Purpose**: Integrates with Google Cloud Speech-to-Text API for audio transcription.

**Key Features**:
- Concurrent transcription of multiple audio files
- Audio format detection and conversion
- Confidence scoring and alternative transcriptions
- Circuit breaker pattern for API resilience
- Word-level timestamps (optional)

### 4. Email Processing Service (`app/services/email_processor.py`)

**Purpose**: Enhances emails with transcriptions and forwards to recipients.

**Key Features**:
- Email content enhancement (plain text and HTML)
- Subject line modification with transcription indicators
- Attachment preservation
- SMTP client with TLS/SSL support
- Template-based email formatting

### 5. File Management Service (`app/services/file_manager.py`)

**Purpose**: Manages temporary file storage and cleanup operations.

**Key Features**:
- Correlation-based file organization
- Atomic file operations
- Automatic cleanup scheduling
- Storage statistics and monitoring
- Disk space monitoring

### 6. Health Monitoring (`health_server.py`, `app/utils/health.py`)

**Purpose**: Provides health checks and monitoring endpoints.

**Key Features**:
- Component health verification
- Kubernetes-compatible probes
- Prometheus metrics export
- Service dependency checking
- Performance monitoring

## Data Flow

### 1. Email Reception Flow

```
Avaya System → SMTP Proxy → Email Parsing → Queue Task → Acknowledge
```

1. Avaya sends voicemail email to SMTP proxy
2. SMTP handler parses email and extracts attachments
3. Creates VoicemailMessage object with correlation ID
4. Queues processing task in Redis
5. Returns success acknowledgment to Avaya

### 2. Processing Flow

```
Celery Worker → File Storage → Transcription → Email Enhancement → Forwarding → Cleanup
```

1. Celery worker picks up queued task
2. Stores audio attachments temporarily
3. Calls Google Speech-to-Text API for transcription
4. Enhances original email with transcription results
5. Forwards enhanced email to recipients
6. Cleans up temporary files

### 3. Error Handling Flow

```
Error Detection → Logging → Retry Logic → Dead Letter Queue → Alert
```

1. Errors detected at each processing stage
2. Structured logging with correlation IDs
3. Automatic retry with exponential backoff
4. Failed tasks moved to dead letter queue
5. Monitoring alerts for critical failures

## Configuration Management

### Environment-Based Configuration

The system uses Pydantic for configuration management with environment variables:

```python
class AppConfig(BaseSettings):
    smtp: SMTPConfig
    google: GoogleConfig
    celery: CeleryConfig
    storage: StorageConfig
    monitoring: MonitoringConfig
```

### Configuration Hierarchy

1. **Environment Variables** (highest priority)
2. **`.env` file**
3. **Default values** (lowest priority)

## Security Architecture

### 1. Network Security

- TLS/SSL encryption for SMTP connections
- Secure API connections to Google Cloud
- Network isolation in container environments
- Firewall rules for port access

### 2. Authentication & Authorization

- SMTP authentication (optional)
- Google Cloud service account authentication
- Container-based isolation
- Secret management for credentials

### 3. Data Protection

- No logging of sensitive email content
- Secure temporary file handling
- Automatic cleanup of processed data
- Input validation and sanitization

## Scalability Design

### 1. Horizontal Scaling

- **SMTP Proxy**: Multiple instances behind load balancer
- **Celery Workers**: Auto-scaling based on queue depth
- **Redis**: Cluster mode for high availability

### 2. Vertical Scaling

- Configurable worker concurrency
- Memory and CPU resource limits
- Storage capacity monitoring

### 3. Performance Optimization

- Async I/O throughout the pipeline
- Connection pooling for external services
- Efficient file handling with streaming
- Caching of frequently accessed data

## Monitoring and Observability

### 1. Structured Logging

```json
{
  "timestamp": "2023-12-01T10:30:00Z",
  "level": "INFO",
  "correlation_id": "req_abc123",
  "message": "Transcription completed",
  "confidence": 0.95,
  "processing_time_ms": 1500
}
```

### 2. Health Checks

- **Liveness**: Service is running
- **Readiness**: Service can handle requests
- **Dependencies**: External service connectivity

### 3. Metrics Collection

- SMTP connection metrics
- Queue depth and processing time
- API response times and error rates
- Storage usage statistics

## Deployment Architecture

### 1. Container Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Host                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │    SMTP     │  │   Celery    │  │       Redis         │  │
│  │   Proxy     │  │  Workers    │  │    (Message         │  │
│  │             │  │ (Scalable)  │  │     Broker)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Health    │  │   Flower    │  │    Persistent       │  │
│  │  Monitor    │  │ (Optional)  │  │     Storage         │  │
│  │             │  │             │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2. Kubernetes Architecture

- **Namespace isolation**
- **ConfigMaps and Secrets**
- **Persistent Volumes**
- **Service discovery**
- **Ingress controllers**

## Error Recovery Strategies

### 1. Transient Failures

- Automatic retry with exponential backoff
- Circuit breaker for external services
- Graceful degradation when services unavailable

### 2. Permanent Failures

- Dead letter queue for manual intervention
- Alert notifications for critical errors
- Fallback processing modes

### 3. Data Consistency

- Atomic file operations
- Transaction-like processing stages
- Correlation ID tracking throughout pipeline

This architecture provides a robust, scalable, and maintainable solution for enterprise voicemail processing with comprehensive monitoring and error handling capabilities.