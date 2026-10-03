# ATLAS Production Deployment Guide

## Overview

This guide covers deploying ATLAS to production environments including Azure, AWS, and Kubernetes.

## Prerequisites

- Docker and Docker Compose
- Terraform or Bicep (for infrastructure)
- kubectl (for Kubernetes)
- Azure CLI, AWS CLI, or equivalent cloud tools
- PostgreSQL 16+
- Redis 7+
- Kafka 7.5+
- Qdrant vector database

## Local Development Deployment

### 1. Setup Environment

```bash
cd /path/to/ATLAS
cp .env.example .env
# Edit .env with your configuration
```

### 2. Start Services

```bash
make dev
```

This starts all services via Docker Compose:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Kafka (port 9092)
- Qdrant (port 6333)
- ATLAS API (port 8000)
- ATLAS Worker
- Prometheus (port 9090)
- Grafana (port 3000)
- Frontend (port 5173)

### 3. Run Tests

```bash
make test
make lint
make type-check
```

## Docker Deployment

### Build Images

```bash
docker build -f Dockerfile.backend -t atlas-api:latest .
docker build -f Dockerfile.worker -t atlas-worker:latest .
```

### Run Containers

```bash
# API
docker run -d \
  --name atlas-api \
  --network host \
  -e DATABASE_URL="postgresql://user:pass@localhost/atlas" \
  -e REDIS_URL="redis://localhost:6379/0" \
  -e KAFKA_BROKERS="localhost:9092" \
  -p 8000:8000 \
  atlas-api:latest

# Worker
docker run -d \
  --name atlas-worker \
  --network host \
  -e DATABASE_URL="postgresql://user:pass@localhost/atlas" \
  -e KAFKA_BROKERS="localhost:9092" \
  -e WORKER_TYPE="ingestion" \
  atlas-worker:latest
```

## Kubernetes Deployment

### Prerequisites

```bash
# Install metrics-server (for HPA)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Create namespace
kubectl create namespace atlas
kubectl config set-context --current --namespace=atlas
```

### Deploy ATLAS

```bash
# Create secrets
kubectl create secret generic atlas-secrets \
  --from-literal=database-url="postgresql://..." \
  --from-literal=llm-api-key="sk-..."

# Create ConfigMap
kubectl create configmap atlas-config \
  --from-literal=redis-url="redis://atlas-redis:6379/0" \
  --from-literal=kafka-brokers="atlas-kafka:29092"

# Apply deployment
kubectl apply -f infrastructure/kubernetes/atlas-deployment.yml
```

### Monitor Deployment

```bash
# Check deployments
kubectl get deployments -n atlas

# View logs
kubectl logs -f deployment/atlas-api -n atlas
kubectl logs -f deployment/atlas-worker-ingestion -n atlas

# Port forward for testing
kubectl port-forward svc/atlas-api 8000:80 -n atlas
```

## Azure Deployment

### Using Terraform

```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan
terraform plan -var="location=eastus" -var="environment=prod"

# Apply
terraform apply -var="location=eastus" -var="environment=prod"
```

### Using Azure Container Instances

```bash
az container create \
  --resource-group atlas-rg \
  --name atlas-api \
  --image atlas-api:latest \
  --ports 8000 \
  --environment-variables \
    DATABASE_HOST=<postgres-host> \
    REDIS_HOST=<redis-host> \
  --cpu 2 \
  --memory 1
```

## AWS Deployment

### Using ECS

```bash
# Create ECS cluster
aws ecs create-cluster --cluster-name atlas

# Register task definition
aws ecs register-task-definition \
  --family atlas-api \
  --network-mode awsvpc \
  --container-definitions '[{"name":"api","image":"atlas-api:latest","portMappings":[{"containerPort":8000}]}]'

# Create service
aws ecs create-service \
  --cluster atlas \
  --service-name atlas-api \
  --task-definition atlas-api \
  --desired-count 3
```

## Configuration Management

### Environment Variables

All sensitive configuration should be managed via environment variables:

```bash
# API
DATABASE_URL=postgresql://user:pass@host/dbname
REDIS_URL=redis://host:6379/0
KAFKA_BROKERS=host1:9092,host2:9092
LLM_API_KEY=sk-...
QDRANT_URL=http://qdrant:6333

# Worker
WORKER_TYPE=ingestion
WORKER_CONCURRENCY=10
```

### Secrets Management

**Azure Key Vault:**
```bash
az keyvault create --name atlas-kv --resource-group atlas-rg
az keyvault secret set --vault-name atlas-kv --name database-url --value "postgresql://..."
```

**AWS Secrets Manager:**
```bash
aws secretsmanager create-secret \
  --name atlas/database-url \
  --secret-string "postgresql://..."
```

## Database Management

### Initialize Database

```bash
# Using CLI
python -m cli.admin init-database

# Using alembic
alembic upgrade head
```

### Create Admin User

```bash
python -m cli.admin create-admin-user \
  --tenant-slug demo \
  --email admin@example.com \
  --password "secure-password"
```

### Backup

```bash
# PostgreSQL
pg_dump -h <host> -U postgres atlas > backup.sql

# Restore
psql -h <host> -U postgres atlas < backup.sql
```

## Monitoring & Observability

### Prometheus Metrics

Access Prometheus dashboard: `http://localhost:9090`

Key metrics to monitor:
- `atlas_api_request_duration_ms` - Request latency
- `atlas_ingestion_documents_total` - Processed documents
- `atlas_cache_hit_rate` - Cache effectiveness
- `atlas_llm_tokens_used` - LLM token usage

### Grafana Dashboards

Access Grafana: `http://localhost:3000`

Pre-configured dashboards:
- API Performance
- Document Ingestion Pipeline
- Vector Database Statistics
- Kafka Consumer Lag

### OpenTelemetry Tracing

Traces exported to `http://localhost:4317`

View traces in Jaeger or similar UI for distributed tracing analysis.

## Health Checks

### Liveness Probe

```bash
curl http://localhost:8000/health
```

### Readiness Probe

```bash
curl http://localhost:8000/ready
```

### Full System Check

```bash
python -c "
import asyncio
from backend.main import app
from backend.config import get_settings

async def check():
    settings = get_settings()
    # Verify all connections
    await settings.verify_connections()
    print('✓ System ready')

asyncio.run(check())
"
```

## Scaling & Performance

### Horizontal Scaling

```bash
# Kubernetes HPA
kubectl autoscale deployment atlas-api \
  --min=2 --max=10 \
  --cpu-percent=70
```

### Connection Pooling

PostgreSQL connection pool size (in config):
```python
SQLALCHEMY_POOL_SIZE = 20  # Main pool
SQLALCHEMY_MAX_OVERFLOW = 10  # Overflow
```

### Cache Warming

```bash
python -c "
from backend.services.cache import SemanticCache
import asyncio

async def warm_cache():
    # Pre-load frequently asked queries
    queries = ['What is machine learning?', ...]
    await cache.warm_cache(queries)

asyncio.run(warm_cache())
"
```

## Troubleshooting

### API Won't Start

```bash
# Check logs
docker logs atlas-api

# Check dependencies
curl http://localhost:5432  # PostgreSQL
redis-cli ping             # Redis
kafka-broker-api-versions  # Kafka
```

### Slow Queries

```bash
# Enable query logging
export SQLALCHEMY_ECHO=true

# Check Prometheus metrics for slow endpoints
# Query: histogram_quantile(0.95, rate(atlas_request_duration_ms[5m]))
```

### Memory Issues

```bash
# Check container memory
docker stats atlas-api

# Reduce batch size
export EMBEDDING_BATCH_SIZE=32
export CHUNK_SIZE=512
```

### Kafka Consumer Lag

```bash
# Check consumer lag
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --group atlas-ingestion-workers \
  --describe

# Scale workers
kubectl scale deployment atlas-worker-ingestion --replicas=5
```

## Production Checklist

- [ ] Database backups configured
- [ ] SSL/TLS certificates installed
- [ ] Firewall rules configured
- [ ] Monitoring and alerts set up
- [ ] Log aggregation configured
- [ ] Secrets rotated
- [ ] Performance baseline established
- [ ] Disaster recovery plan tested
- [ ] Rate limiting enabled
- [ ] CORS configured for frontend
- [ ] HTTPS enforced
- [ ] Health checks passing
- [ ] Load tests completed
- [ ] Security scan completed
- [ ] Documentation updated

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/atlas/issues
- Documentation: See README.md
- Email: support@atlas.example.com
