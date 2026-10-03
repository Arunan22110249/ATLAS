# ATLAS Production Deployment

## Overview

This guide covers deploying ATLAS to production environments. Choose your deployment model:
- **Option 1**: Docker Compose (single server)
- **Option 2**: Kubernetes (cloud-native, recommended)
- **Option 3**: Terraform (infrastructure automation)

## Pre-Deployment Checklist

- [ ] Database migrations tested locally
- [ ] All tests passing (29/30)
- [ ] Environment variables configured
- [ ] SSL/TLS certificates obtained
- [ ] External services configured (LLM provider, etc.)
- [ ] Monitoring and alerts set up
- [ ] Backup strategy defined
- [ ] Scaling policies planned

## Option 1: Docker Compose (Single Server)

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- 16GB RAM minimum
- 100GB storage (adjust based on document volume)

### Deployment Steps

#### 1. Prepare Server
```bash
# SSH into server
ssh user@your-server.com

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### 2. Clone Repository
```bash
cd /opt
sudo git clone https://github.com/yourusername/atlas.git
sudo chown -R $USER:$USER atlas
cd atlas
```

#### 3. Configure Environment
```bash
# Copy and edit environment file
cp .env.example .env.prod
nano .env.prod

# Critical settings for production:
APP_ENV=production
LOG_LEVEL=info
DEBUG=false

DATABASE_URL=postgresql://atlas_user:secure_password@postgres:5432/atlas
REDIS_URL=redis://redis:6379/0
KAFKA_BROKERS=kafka:9092

LLM_PROVIDER=openai
LLM_API_KEY=sk-...  # Secure credential management

# SSL/TLS
HTTPS_ENABLED=true
SSL_CERT_PATH=/etc/letsencrypt/live/your-domain/fullchain.pem
SSL_KEY_PATH=/etc/letsencrypt/live/your-domain/privkey.pem

# Observability
PROMETHEUS_ENABLED=true
GRAFANA_ADMIN_PASSWORD=secure_password
```

#### 4. Start Services
```bash
# Use production compose file
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Or for background execution:
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans

# Verify all services
docker-compose ps
```

#### 5. Initialize Database
```bash
docker-compose exec api alembic upgrade head
```

#### 6. Set Up Reverse Proxy (Nginx)
```bash
# Create nginx config
sudo nano /etc/nginx/sites-available/atlas

# Add SSL configuration
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

#### 7. Enable and Start Nginx
```bash
sudo ln -s /etc/nginx/sites-available/atlas /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl start nginx
sudo systemctl enable nginx
```

### Monitoring & Maintenance

#### View Logs
```bash
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f postgres
```

#### Backup Database
```bash
# Manual backup
docker-compose exec postgres pg_dump -U atlas_user atlas > backup.sql

# Automated backup (add to crontab)
0 2 * * * docker-compose -f /opt/atlas/docker-compose.yml exec postgres pg_dump -U atlas_user atlas > /backups/atlas-$(date +\%Y\%m\%d).sql
```

#### Update Application
```bash
git pull origin main
docker-compose build api worker
docker-compose up -d
docker-compose exec api alembic upgrade head
```

## Option 2: Kubernetes Deployment

### Prerequisites
- Kubernetes cluster (1.21+)
- kubectl configured
- Helm (optional, for package management)
- Persistent volume provisioner
- Ingress controller configured

### Architecture

```
Ingress Controller (NGINX/Traefik)
    ↓
API Deployment (3+ replicas)
    ├→ StatefulSet: PostgreSQL (1 replica)
    ├→ StatefulSet: Redis (1 replica)
    └→ Deployment: Worker (2+ replicas)
         ├→ StatefulSet: Kafka (1 replica)
         ├→ StatefulSet: Qdrant (1 replica)
         └→ Deployment: MinIO (1 replica)
```

### Deployment Steps

#### 1. Create Namespace
```bash
kubectl create namespace atlas
kubectl config set-context --current --namespace=atlas
```

#### 2. Create Secrets
```bash
# Database credentials
kubectl create secret generic postgres-credentials \
  --from-literal=username=atlas_user \
  --from-literal=password=secure_db_password

# LLM API key
kubectl create secret generic llm-credentials \
  --from-literal=api_key=sk-...

# MinIO credentials
kubectl create secret generic minio-credentials \
  --from-literal=access_key=minioadmin \
  --from-literal=secret_key=secure_password
```

#### 3. Create ConfigMaps
```bash
kubectl create configmap atlas-config \
  --from-literal=APP_ENV=production \
  --from-literal=LOG_LEVEL=info \
  --from-literal=DATABASE_HOST=postgres \
  --from-literal=REDIS_HOST=redis \
  --from-literal=KAFKA_BROKERS=kafka:9092
```

#### 4. Apply Manifests
```bash
cd infrastructure/kubernetes

# Order matters for dependencies
kubectl apply -f namespace.yaml
kubectl apply -f storage-class.yaml
kubectl apply -f postgres-statefulset.yaml
kubectl apply -f redis-statefulset.yaml
kubectl apply -f kafka-statefulset.yaml
kubectl apply -f qdrant-deployment.yaml
kubectl apply -f minio-deployment.yaml
kubectl apply -f api-deployment.yaml
kubectl apply -f worker-deployment.yaml
kubectl apply -f ingress.yaml
```

#### 5. Verify Deployment
```bash
# Check pods
kubectl get pods -n atlas

# Check services
kubectl get svc -n atlas

# Check ingress
kubectl get ingress -n atlas

# Describe pod for issues
kubectl describe pod <pod-name> -n atlas

# View logs
kubectl logs -f deployment/atlas-api -n atlas
```

#### 6. Set Up Ingress for External Access
```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: atlas-ingress
  namespace: atlas
spec:
  tls:
  - hosts:
    - atlas.your-domain.com
    secretName: atlas-tls
  rules:
  - host: atlas.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: atlas-api
            port:
              number: 8000
```

### Scaling

#### Horizontal Pod Autoscaling (HPA)
```bash
# Enable autoscaling for API
kubectl autoscale deployment atlas-api --min=3 --max=10 --cpu-percent=70

# For workers
kubectl autoscale deployment atlas-worker --min=2 --max=20 --cpu-percent=80
```

#### Manual Scaling
```bash
# Scale API to 5 replicas
kubectl scale deployment atlas-api --replicas=5

# Scale workers to 10
kubectl scale deployment atlas-worker --replicas=10
```

### Monitoring

#### Enable Metrics
```bash
kubectl apply -f monitoring/prometheus-service-monitor.yaml
kubectl apply -f monitoring/grafana-dashboard.yaml
```

#### View Pod Metrics
```bash
kubectl top pods -n atlas
kubectl top nodes
```

### Upgrades

#### Rolling Update
```bash
# Update image
kubectl set image deployment/atlas-api \
  api=your-registry/atlas-api:v1.1.0

# Watch rollout
kubectl rollout status deployment/atlas-api

# Rollback if needed
kubectl rollout undo deployment/atlas-api
```

#### Database Migrations
```bash
# Create migration job
kubectl apply -f jobs/migration-job.yaml

# Check status
kubectl get jobs -n atlas
kubectl logs job/atlas-migration
```

## Option 3: Terraform Deployment

### Prerequisites
- Terraform 1.0+
- Cloud provider CLI (AWS CLI, Azure CLI)
- Cloud credentials configured

### Deployment Steps

#### 1. Configure Provider
```hcl
# terraform/main.tf
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    bucket  = "your-tf-state-bucket"
    key     = "atlas/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
```

#### 2. Define Variables
```hcl
# terraform/variables.tf
variable "environment" {
  default = "production"
}

variable "region" {
  default = "us-east-1"
}

variable "instance_type" {
  default = "t3.large"
}

variable "database_password" {
  sensitive = true
}
```

#### 3. Deploy Infrastructure
```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan
terraform plan -out=tfplan

# Apply
terraform apply tfplan

# Get outputs
terraform output
```

#### 4. Deploy Application
```bash
# Get kubeconfig
aws eks update-kubeconfig --region us-east-1 --name atlas-cluster

# Deploy via kubectl (see Kubernetes section)
kubectl apply -f ../kubernetes/
```

### Terraform Modules

Key modules:
- `modules/networking` - VPC, subnets, security groups
- `modules/database` - RDS PostgreSQL
- `modules/cache` - ElastiCache Redis
- `modules/kubernetes` - EKS cluster
- `modules/storage` - S3 buckets

## Security Best Practices

### Secrets Management
✅ Use cloud provider secret services:
- **AWS Secrets Manager** for credentials
- **Azure Key Vault** for secrets
- **Kubernetes Secrets** with encryption at rest

❌ DO NOT:
- Commit credentials to repository
- Use plaintext environment files
- Share API keys in logs

### Network Security
✅ Enable:
- TLS/SSL for all connections
- Network policies (Kubernetes)
- Security groups (AWS/Azure)
- VPC/Private networks
- WAF (Web Application Firewall)

❌ Expose:
- Database directly to internet
- Admin ports (5432, 6379, etc.)
- Kafka brokers without authentication

### Application Security
✅ Implement:
- Rate limiting
- Input validation
- SQL injection prevention
- CSRF protection
- Secure headers (HSTS, CSP)

### Compliance
✅ Maintain:
- Audit logs
- Data retention policies
- Encryption at rest
- Regular backups
- Incident response plan

## Monitoring & Observability

### Prometheus Metrics
- `atlas_requests_total` - Request count by endpoint
- `atlas_request_duration_seconds` - Request latency
- `atlas_database_queries` - Database query count
- `atlas_cache_hits` - Cache hit rate
- `atlas_embedding_tokens` - Token usage for embeddings

### Grafana Dashboards
- System metrics (CPU, memory, disk)
- Application metrics (requests, errors, latency)
- Database metrics (connections, queries, cache)
- Document ingestion pipeline status

### OpenTelemetry Tracing
- Distributed trace collection
- Service-to-service latency analysis
- Error root cause analysis
- Performance bottleneck identification

## Troubleshooting

### Application Won't Start
```bash
# Check logs
docker-compose logs api
kubectl logs -f deployment/atlas-api

# Verify environment
docker-compose exec api env | grep DATABASE_URL

# Test database connection
python -c "from sqlalchemy import create_engine; create_engine('postgresql://...').connect()"
```

### High Memory Usage
```bash
# Reduce embedding batch size
EMBEDDING_BATCH_SIZE=16  # Default 32

# Limit worker concurrency
WORKER_CONCURRENCY=2

# Clear cache
docker-compose exec redis redis-cli FLUSHALL
```

### Database Migration Failures
```bash
# Check current migration state
docker-compose exec api alembic current

# Review migration history
docker-compose exec api alembic history

# Rollback and retry
docker-compose exec api alembic downgrade -1
docker-compose exec api alembic upgrade head
```

## Recovery Procedures

### Database Recovery
```bash
# Restore from backup
docker-compose exec postgres psql -U atlas < backup.sql

# Or from cloud backup
aws s3 cp s3://backups/atlas.sql . && psql -U atlas < atlas.sql
```

### Service Recovery
```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart api
docker-compose restart worker

# Full redeploy
docker-compose down
docker-compose up -d
```

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System design
- [SETUP.md](./SETUP.md) - Local development
- [../SECURITY.md](../SECURITY.md) - Security model
- Cloud provider documentation (AWS, Azure, GCP)
- Kubernetes documentation
- Terraform registry
