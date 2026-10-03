# ATLAS Local Development Setup

## Prerequisites

### Required
- **Python 3.12+** (3.13.x recommended for latest features)
- **Git**
- **Docker** (optional, for containerized setup)
- **Docker Compose** (optional, for full stack)

### Optional
- **PostgreSQL 16** (if running without Docker)
- **Redis 7** (if running without Docker)
- **Kafka 3** (if running without Docker)
- **Make** (for convenience commands)

## Quick Start (Docker Compose)

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/atlas.git
cd atlas
```

### 2. Configure Environment
```bash
cp .env.example .env
# Review and edit .env with your settings
```

### 3. Start All Services
```bash
docker-compose up -d
```

This starts 11 services:
- PostgreSQL 16
- Redis 7
- Kafka + Zookeeper
- Qdrant
- MinIO
- Prometheus
- Grafana
- ATLAS Backend API
- ATLAS Frontend
- OpenTelemetry Collector
- pgAdmin (optional admin panel)

### 4. Verify Services
```bash
# Check all containers are running
docker-compose ps

# View logs for a specific service
docker-compose logs -f api

# Check API health
curl http://localhost:8000/health

# Access frontend
open http://localhost:5173
```

### 5. Initialize Database
```bash
# Apply migrations
docker-compose exec api alembic upgrade head
```

## Local Development (Without Docker)

### 1. Python Environment Setup
```bash
# Create virtual environment
python -m venv .venv

# Activate
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Development Tools
```bash
pip install pytest pytest-asyncio pytest-cov black ruff mypy
```

### 4. Database Setup

#### Option A: Use Docker for databases only
```bash
docker-compose up -d postgres redis kafka zookeeper
```

#### Option B: Install PostgreSQL locally
```bash
# macOS with Homebrew
brew install postgresql
brew services start postgresql

# Create database
createdb atlas
psql atlas < schema.sql

# Or using psycopg2 connection:
python -c "
from sqlalchemy import create_engine
from backend.models import Base
engine = create_engine('postgresql://localhost/atlas')
Base.metadata.create_all(engine)
"
```

### 5. Run Migrations
```bash
alembic upgrade head
```

### 6. Environment Configuration
Create `.env.local`:
```bash
# Database
DATABASE_URL=postgresql://localhost:5432/atlas
DATABASE_ECHO=true  # Log SQL queries

# Cache
REDIS_URL=redis://localhost:6379/0

# Message Queue
KAFKA_BROKERS=localhost:9092

# LLM (Optional - requires API key)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# Vector Database
QDRANT_URL=http://localhost:6333

# Object Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=atlas

# Observability
PROMETHEUS_ENDPOINT=http://localhost:9090
OTEL_ENABLED=true

# Application
APP_ENV=development
LOG_LEVEL=debug
```

### 7. Start API Server
```bash
# Simple start
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Or with make
make dev

# Or using the Makefile run command
make run-api
```

### 8. Start Ingestion Worker (Optional)
```bash
# In a separate terminal
python backend/workers/ingestion_worker.py

# Or
make run-worker
```

### 9. Access Services
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **ReDoc**: http://localhost:8000/redoc (API Reference)
- **Frontend**: http://localhost:5173 (Vite dev server)
- **Grafana**: http://localhost:3000 (Dashboards)
- **Prometheus**: http://localhost:9090 (Metrics)

## Testing

### Unit Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run specific test
pytest tests/test_auth.py::test_hash_password -v

# Run with coverage
pytest tests/ --cov=backend --cov-report=html
# View coverage report
open htmlcov/index.html
```

### Test Organization
- `tests/test_auth.py` - Authentication and JWT
- `tests/test_cache.py` - Redis caching
- `tests/test_documents.py` - Document CRUD and deduplication
- `tests/test_retrieval.py` - Search algorithms (dense, BM25, RRF)
- `tests/integration_tests.py` - End-to-end workflows (designed, not automated)

### Expected Results
```
29 passed, 1 skipped, 56 warnings in ~46s
Coverage: 39% (auth 82%, cache 66%, documents 62%, retrieval 36%)
```

## Code Quality

### Format Code (Black)
```bash
black backend/ tests/ frontend/
```

### Lint Code (Ruff)
```bash
ruff check backend/ tests/
ruff check --fix backend/ tests/  # Auto-fix
```

### Type Checking (MyPy)
```bash
mypy backend/ --ignore-missing-imports
```

**Note**: 73 type errors in integration-level services (not blocking for release). Core services are properly typed.

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
psql -l

# Verify connection string in .env
DATABASE_URL=postgresql://user:password@localhost:5432/atlas

# Test connection
python -c "import sqlalchemy; print(sqlalchemy.create_engine('postgresql://localhost/atlas'))"
```

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping  # Should return PONG

# Verify Redis URL in .env
REDIS_URL=redis://localhost:6379/0
```

### Kafka Connection Issues
```bash
# Check Kafka broker is running
docker-compose ps kafka

# Verify broker address
KAFKA_BROKERS=localhost:9092

# Test producer
python -c "
from kafka import KafkaProducer
p = KafkaProducer(bootstrap_servers='localhost:9092')
p.send('test', b'hello').get(timeout=5)
"
```

### Migration Errors
```bash
# Check migration history
alembic current
alembic history

# Rollback last migration
alembic downgrade -1

# Recreate from scratch
alembic downgrade base  # Removes all tables
alembic upgrade head    # Reapplies all migrations
```

### Port Already in Use
```bash
# Find process using port
lsof -i :8000  # macOS/Linux
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess  # Windows

# Kill process or use different port
python -m uvicorn backend.main:app --port 8001
```

### Memory/Performance Issues
```bash
# Reduce vector dimension for testing
# Edit backend/services/embedding.py:
# EMBEDDING_DIM = 384  → Try 128 for testing

# Reduce Kafka partitions for testing
# Edit docker-compose.yml:
# KAFKA_NUM_PARTITIONS=1

# Disable OpenTelemetry tracing
OTEL_ENABLED=false
```

## Development Workflow

### Add a New Endpoint
1. Define request/response schema in `backend/schemas.py`
2. Implement service logic in `backend/services/`
3. Add route handler in `backend/main.py`
4. Write tests in `tests/test_*.py`
5. Run `pytest tests/` to verify

### Add a New Service
1. Create file `backend/services/my_service.py`
2. Implement async service class
3. Add to `backend/main.py` initialization
4. Create `tests/test_my_service.py`
5. Verify multi-tenant isolation with `tenant_id` checks

### Debug Request Flow
```python
# In backend/config.py, enable logging:
LOG_LEVEL=debug

# View structured logs:
python -m uvicorn backend.main:app --log-config logging.yaml

# Use debugger:
import pdb; pdb.set_trace()  # Or use IDE breakpoints
```

### Performance Profiling
```bash
# CPU profiling
python -m cProfile -o stats.prof backend/main.py
python -m pstats stats.prof

# Memory profiling
pip install memory-profiler
python -m memory_profiler backend/main.py

# Async profiling (Python 3.12+)
# See docs/ARCHITECTURE.md for details
```

## GitHub Actions CI/CD

The repository includes `.github/workflows/` for automated testing:
- **On push**: Run pytest, coverage, linting
- **On PR**: Same checks + review comments
- **On release**: Build Docker images, push to registry

## Production Deployment

For deployment to cloud environments, see [DEPLOYMENT.md](./DEPLOYMENT.md).

Quick reference:
- **Docker**: `docker build -f Dockerfile.backend -t atlas-api:latest .`
- **Kubernetes**: `kubectl apply -f infrastructure/kubernetes/`
- **Terraform**: `terraform apply -f infrastructure/terraform/`
