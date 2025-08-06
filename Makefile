# SMTP Voicemail Proxy Makefile

.PHONY: help build up down logs shell test clean lint format

# Default target
help:
	@echo "Available commands:"
	@echo "  build     - Build Docker images"
	@echo "  up        - Start all services"
	@echo "  down      - Stop all services"
	@echo "  logs      - Show logs from all services"
	@echo "  shell     - Open shell in smtp-proxy container"
	@echo "  test      - Run tests"
	@echo "  clean     - Clean up containers and volumes"
	@echo "  lint      - Run code linting"
	@echo "  format    - Format code"
	@echo "  dev       - Start development environment"
	@echo "  prod      - Start production environment"

# Build Docker images
build:
	docker compose build

# Start all services
up:
	docker compose up -d

# Start development environment with tools
dev:
	docker compose --profile dev-tools up -d

# Stop development environment with tools
dev-stop:
	docker compose --profile dev-tools down

# Start production environment
prod:
	docker compose -f docker compose.yml up -d

# Stop all services
down:
	docker compose down

# Show logs
logs:
	docker compose logs -f

# Show logs for specific service
logs-smtp:
	docker compose logs -f smtp-proxy

logs-worker:
	docker compose logs -f celery-worker

logs-redis:
	docker compose logs -f redis

# Open shell in smtp-proxy container
shell:
	docker compose exec smtp-proxy /bin/bash

# Run tests
test:
	docker compose exec smtp-proxy python -m pytest tests/ -v

# Clean up everything
clean:
	docker compose down -v --remove-orphans
	docker system prune -f

# Code quality
lint:
	docker compose exec smtp-proxy python -m black --check .
	docker compose exec smtp-proxy python -m isort --check-only .
	docker compose exec smtp-proxy python -m mypy app/

format:
	docker compose exec smtp-proxy python -m black .
	docker compose exec smtp-proxy python -m isort .

# Health checks
health:
	curl -s http://localhost:8000/health | jq .

ready:
	curl -s http://localhost:8000/health/ready | jq .

metrics:
	curl -s http://localhost:8000/metrics

# Monitoring
flower:
	@echo "Flower monitoring available at: http://localhost:5555"
	@echo "Default credentials: admin/admin"

redis-insight:
	@echo "Redis Insight available at: http://localhost:8001"

# Development utilities
install-dev:
	pip install -r requirements.txt
	pip install pre-commit
	pre-commit install

send-test-email:
	@echo "Sending test email to SMTP proxy..."
	python scripts/send_test_email.py

# Backup and restore
backup-redis:
	docker compose exec redis redis-cli BGSAVE
	docker cp voicemail-proxy-redis:/data/dump.rdb ./backup/redis-$(shell date +%Y%m%d-%H%M%S).rdb

# View configuration
config:
	docker compose config

# Show service status
status:
	docker compose ps

# Restart specific service
restart-smtp:
	docker compose restart smtp-proxy

restart-worker:
	docker compose restart celery-worker

restart-redis:
	docker compose restart redis