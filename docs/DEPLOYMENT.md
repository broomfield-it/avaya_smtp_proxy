# Deployment Guide

This guide covers deploying the SMTP Voicemail Proxy in various environments.

## Prerequisites

### Required Services

1. **Google Cloud Platform Account**
   - Speech-to-Text API enabled
   - Service account with appropriate permissions
   - Billing account configured

2. **SMTP Server**
   - Outbound SMTP server for forwarding emails
   - Authentication credentials
   - Network connectivity from deployment environment

3. **Infrastructure**
   - Docker and Docker Compose (for container deployment)
   - Redis server (included in Docker Compose)
   - Persistent storage for temporary files

### Google Cloud Setup

1. **Create a GCP Project:**
   ```bash
   gcloud projects create your-voicemail-project
   gcloud config set project your-voicemail-project
   ```

2. **Enable Speech-to-Text API:**
   ```bash
   gcloud services enable speech.googleapis.com
   ```

3. **Create Service Account:**
   ```bash
   gcloud iam service-accounts create voicemail-proxy \
     --display-name="Voicemail Proxy Service Account"
   
   gcloud projects add-iam-policy-binding your-voicemail-project \
     --member="serviceAccount:voicemail-proxy@your-voicemail-project.iam.gserviceaccount.com" \
     --role="roles/speech.client"
   
   gcloud iam service-accounts keys create credentials/service-account.json \
     --iam-account=voicemail-proxy@your-voicemail-project.iam.gserviceaccount.com
   ```

## Docker Deployment

### 1. Basic Setup

1. **Clone repository:**
   ```bash
   git clone <repository-url>
   cd avaya_smtp_proxy
   ```

2. **Create directories:**
   ```bash
   mkdir -p credentials logs backup
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Add Google credentials:**
   ```bash
   # Copy your service-account.json to credentials/
   cp /path/to/service-account.json credentials/
   ```

5. **Start services:**
   ```bash
   docker-compose up -d
   ```

### 2. Production Configuration

**docker-compose.prod.yml:**
```yaml
version: '3.8'

services:
  smtp-proxy:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
    environment:
      - LOG_LEVEL=INFO
      - ENVIRONMENT=production
    volumes:
      - ./credentials:/app/credentials:ro
      - smtp_storage:/app/storage
      - smtp_logs:/app/logs
    networks:
      - voicemail-network

  celery-worker:
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
    environment:
      - CELERY_WORKER_CONCURRENCY=4
    volumes:
      - ./credentials:/app/credentials:ro
      - smtp_storage:/app/storage
      - smtp_logs:/app/logs

  redis:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.25'
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 200mb --maxmemory-policy allkeys-lru

volumes:
  smtp_storage:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/voicemail-proxy/storage
  
  smtp_logs:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/voicemail-proxy/logs
  
  redis_data:
    driver: local
```

**Start production deployment:**
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Kubernetes Deployment

### 1. Namespace and ConfigMap

**namespace.yaml:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: voicemail-proxy
```

**configmap.yaml:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: voicemail-proxy-config
  namespace: voicemail-proxy
data:
  SMTP_HOST: "0.0.0.0"
  SMTP_PORT: "1025"
  GOOGLE_LANGUAGE_CODE: "en-US"
  GOOGLE_MODEL: "telephony"
  CELERY_WORKER_CONCURRENCY: "4"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
  STORAGE_PATH: "/app/storage"
  STORAGE_CLEANUP_AFTER_HOURS: "24"
```

### 2. Secrets

**secret.yaml:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: voicemail-proxy-secrets
  namespace: voicemail-proxy
type: Opaque
data:
  OUTBOUND_SMTP_HOST: <base64-encoded-smtp-host>
  OUTBOUND_SMTP_USER: <base64-encoded-smtp-user>
  OUTBOUND_SMTP_PASSWORD: <base64-encoded-smtp-password>
  GOOGLE_PROJECT_ID: <base64-encoded-project-id>
  service-account.json: <base64-encoded-service-account-json>
```

### 3. Persistent Storage

**pvc.yaml:**
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: voicemail-storage
  namespace: voicemail-proxy
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
  storageClassName: standard
```

### 4. Redis Deployment

**redis-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: voicemail-proxy
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        command: ["redis-server", "--appendonly", "yes"]
        volumeMounts:
        - name: redis-storage
          mountPath: /data
        resources:
          limits:
            memory: "256Mi"
            cpu: "250m"
          requests:
            memory: "128Mi"
            cpu: "100m"
      volumes:
      - name: redis-storage
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: voicemail-proxy
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
```

### 5. SMTP Proxy Deployment

**smtp-proxy-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smtp-proxy
  namespace: voicemail-proxy
spec:
  replicas: 2
  selector:
    matchLabels:
      app: smtp-proxy
  template:
    metadata:
      labels:
        app: smtp-proxy
    spec:
      containers:
      - name: smtp-proxy
        image: voicemail-proxy:latest
        ports:
        - containerPort: 1025
          name: smtp
        - containerPort: 8000
          name: health
        envFrom:
        - configMapRef:
            name: voicemail-proxy-config
        - secretRef:
            name: voicemail-proxy-secrets
        env:
        - name: CELERY_BROKER_URL
          value: "redis://redis:6379/0"
        - name: CELERY_RESULT_BACKEND
          value: "redis://redis:6379/0"
        - name: GOOGLE_APPLICATION_CREDENTIALS
          value: "/app/credentials/service-account.json"
        volumeMounts:
        - name: storage
          mountPath: /app/storage
        - name: credentials
          mountPath: /app/credentials
          readOnly: true
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          limits:
            memory: "512Mi"
            cpu: "500m"
          requests:
            memory: "256Mi"
            cpu: "250m"
      - name: health-server
        image: voicemail-proxy:latest
        command: ["python", "health_server.py"]
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: voicemail-proxy-config
        - secretRef:
            name: voicemail-proxy-secrets
        resources:
          limits:
            memory: "128Mi"
            cpu: "100m"
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: voicemail-storage
      - name: credentials
        secret:
          secretName: voicemail-proxy-secrets
          items:
          - key: service-account.json
            path: service-account.json

---
apiVersion: v1
kind: Service
metadata:
  name: smtp-proxy
  namespace: voicemail-proxy
spec:
  selector:
    app: smtp-proxy
  ports:
  - name: smtp
    port: 1025
    targetPort: 1025
  - name: health
    port: 8000
    targetPort: 8000
  type: LoadBalancer
```

### 6. Celery Worker Deployment

**celery-worker-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
  namespace: voicemail-proxy
spec:
  replicas: 3
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      containers:
      - name: celery-worker
        image: voicemail-proxy:latest
        command: ["celery", "-A", "app.tasks.worker", "worker", "--loglevel=INFO"]
        envFrom:
        - configMapRef:
            name: voicemail-proxy-config
        - secretRef:
            name: voicemail-proxy-secrets
        env:
        - name: CELERY_BROKER_URL
          value: "redis://redis:6379/0"
        - name: CELERY_RESULT_BACKEND
          value: "redis://redis:6379/0"
        - name: GOOGLE_APPLICATION_CREDENTIALS
          value: "/app/credentials/service-account.json"
        volumeMounts:
        - name: storage
          mountPath: /app/storage
        - name: credentials
          mountPath: /app/credentials
          readOnly: true
        resources:
          limits:
            memory: "1Gi"
            cpu: "1000m"
          requests:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          exec:
            command:
            - celery
            - -A
            - app.tasks.worker
            - inspect
            - ping
          initialDelaySeconds: 60
          periodSeconds: 30
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: voicemail-storage
      - name: credentials
        secret:
          secretName: voicemail-proxy-secrets
          items:
          - key: service-account.json
            path: service-account.json
```

### 7. Deploy to Kubernetes

```bash
# Apply configurations
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f pvc.yaml
kubectl apply -f redis-deployment.yaml
kubectl apply -f smtp-proxy-deployment.yaml
kubectl apply -f celery-worker-deployment.yaml

# Check deployment status
kubectl get pods -n voicemail-proxy
kubectl get services -n voicemail-proxy

# View logs
kubectl logs -f deployment/smtp-proxy -n voicemail-proxy
kubectl logs -f deployment/celery-worker -n voicemail-proxy
```

## Monitoring and Maintenance

### 1. Health Checks

```bash
# Check service health
curl http://smtp-proxy-service:8000/health

# Check readiness
curl http://smtp-proxy-service:8000/health/ready

# View metrics
curl http://smtp-proxy-service:8000/metrics
```

### 2. Log Management

**Structured logging with centralized collection:**

```yaml
# Add to deployment
- name: LOG_FORMAT
  value: "json"
- name: LOG_LEVEL
  value: "INFO"
```

**Log aggregation with Fluentd/Fluent Bit:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
data:
  fluent-bit.conf: |
    [INPUT]
        Name tail
        Path /var/log/containers/*voicemail-proxy*.log
        Parser docker
        Tag voicemail.*
    
    [OUTPUT]
        Name elasticsearch
        Match voicemail.*
        Host elasticsearch
        Port 9200
        Index voicemail-logs
```

### 3. Backup and Recovery

**Redis backup:**
```bash
# Manual backup
kubectl exec -it redis-pod -- redis-cli BGSAVE
kubectl cp redis-pod:/data/dump.rdb ./redis-backup.rdb

# Restore
kubectl cp ./redis-backup.rdb redis-pod:/data/dump.rdb
kubectl rollout restart deployment/redis
```

**Storage backup:**
```bash
# Backup persistent volume
kubectl create job backup-storage --image=busybox -- tar czf /backup/storage-$(date +%Y%m%d).tar.gz /app/storage
```

### 4. Scaling

**Horizontal scaling:**
```bash
# Scale SMTP proxy
kubectl scale deployment smtp-proxy --replicas=3

# Scale Celery workers
kubectl scale deployment celery-worker --replicas=5
```

**Vertical scaling:**
```yaml
# Update resource limits
resources:
  limits:
    memory: "2Gi"
    cpu: "2000m"
  requests:
    memory: "1Gi"
    cpu: "1000m"
```

## Troubleshooting

### Common Issues

1. **SMTP Connection Issues:**
   ```bash
   # Check service connectivity
   kubectl exec -it smtp-proxy-pod -- telnet smtp.company.com 587
   
   # Verify credentials
   kubectl get secret voicemail-proxy-secrets -o yaml
   ```

2. **Google API Issues:**
   ```bash
   # Check service account permissions
   kubectl exec -it smtp-proxy-pod -- gcloud auth list
   
   # Test API connectivity
   kubectl exec -it smtp-proxy-pod -- python -c "
   from google.cloud import speech
   client = speech.SpeechClient()
   print('Google API connection successful')
   "
   ```

3. **Storage Issues:**
   ```bash
   # Check PVC status
   kubectl get pvc -n voicemail-proxy
   
   # Check disk space
   kubectl exec -it smtp-proxy-pod -- df -h /app/storage
   ```

### Performance Monitoring

**Prometheus metrics collection:**
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: voicemail-proxy
spec:
  selector:
    matchLabels:
      app: smtp-proxy
  endpoints:
  - port: health
    path: /metrics
```

**Key metrics to monitor:**
- SMTP connection rate and duration
- Queue depth and processing time
- Google API response time and error rate
- Storage usage and cleanup frequency
- Memory and CPU utilization

This deployment guide provides a comprehensive approach to deploying the SMTP Voicemail Proxy in various environments with proper monitoring, scaling, and maintenance procedures.