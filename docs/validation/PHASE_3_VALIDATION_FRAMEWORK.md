# ATLAS Phase 3: Integration & Infrastructure Validation Framework
## Comprehensive Testing Guide & Procedure

**Status**: Framework Created for Execution in Proper Environment  
**Prerequisites**: Docker Desktop or Docker Server + PostgreSQL 16  
**Estimated Time**: 4-6 hours  

---

## PART 1: INFRASTRUCTURE SETUP & VALIDATION

### Step 1.1: Prepare Clean Environment

```bash
# Stop and remove existing containers
docker compose down -v

# Remove images for fresh build
docker rmi atlas-api atlas-worker -f 2>/dev/null || true

# Verify clean state
docker ps -a
docker images | grep atlas
```

**Expected Result**: No ATLAS containers or images running.

---

### Step 1.2: Build Docker Images

```bash
cd /path/to/ATLAS

# Build with no cache for clean environment
docker compose build --no-cache

# Verify images are created
docker images | grep atlas
```

**Expected Output**:
```
atlas-api         latest    <hash>    <size>
atlas-worker      latest    <hash>    <size>
```

**Validation Checklist**:
- [ ] Both Dockerfiles build without errors
- [ ] No layer caching issues
- [ ] Images include all dependencies (from requirements.txt)

---

### Step 1.3: Start Docker Compose Stack

```bash
# Start all services
docker compose up -d

# Monitor startup progress
docker compose logs -f

# Check all services are running
docker compose ps
```

**Expected Services**:
1. ✅ postgres:5432 (healthy)
2. ✅ redis:6379 (healthy)
3. ✅ kafka:9092 (started)
4. ✅ zookeeper:2181 (started)
5. ✅ qdrant:6333 (healthy)
6. ✅ minio:9000 (healthy)
7. ✅ api:8000 (running)
8. ✅ worker-ingestion (running)
9. ✅ frontend:5173 (running)
10. ✅ prometheus:9090 (running)
11. ✅ grafana:3000 (running)
12. ✅ otel-collector:4317 (running)

**Health Check Procedure**:
```bash
# Check health status
docker compose ps --format "table {{.Service}}\t{{.Status}}"

# View specific service logs
docker compose logs postgres      # Should show "database system is ready"
docker compose logs redis         # Should show "Ready to accept connections"
docker compose logs qdrant        # Should show "Started Qdrant"
docker compose logs api           # Should show "Uvicorn running on 0.0.0.0:8000"
docker compose logs worker        # Should show "Starting ingestion worker"
```

---

### Step 1.4: Service Connectivity Validation

```bash
# Test PostgreSQL connection
psql -h localhost -U atlas -d atlas -c "SELECT version();"

# Test Redis connection
redis-cli -h localhost ping

# Test Kafka connectivity
docker exec atlas-kafka kafka-broker-api-versions.sh \
  --bootstrap-server localhost:9092

# Test Qdrant
curl -s http://localhost:6333/health | jq .

# Test MinIO
curl -s http://localhost:9000/minio/health/live

# Test API
curl -s http://localhost:8000/health | jq .

# Test Prometheus
curl -s http://localhost:9090/-/healthy

# Test Grafana (should redirect to login)
curl -i http://localhost:3000/api/health
```

**Expected Results**:
- ✅ PostgreSQL returns version info
- ✅ Redis returns PONG
- ✅ Kafka broker is responding
- ✅ Qdrant returns {"status":"ok"}
- ✅ MinIO returns 200 OK
- ✅ API returns health status
- ✅ Prometheus returns 200 OK
- ✅ Grafana returns 200 OK

---

## PART 2: DATABASE MIGRATION VALIDATION

### Step 2.1: Verify Alembic Migrations Ran

```bash
# Check migration status
docker exec atlas-api alembic current

# View migration history
docker exec atlas-api alembic history

# Verify schema created
docker exec atlas-postgres psql -U atlas -d atlas -c "\dt"
```

**Expected Output**:
```
                      List of relations
 Schema |        Name        | Type  |    Owner
--------+--------------------+-------+----------
 public | alembic_version    | table | atlas
 public | alembic_version    | table | atlas
 public | tenant             | table | atlas
 public | user_account       | table | atlas
 public | tenant_membership  | table | atlas
 public | collection         | table | atlas
 public | document           | table | atlas
 public | document_version   | table | atlas
 public | chunk              | table | atlas
 public | processing_job     | table | atlas
 public | evaluation_run     | table | atlas
```

### Step 2.2: Verify Schema Integrity

```bash
# Check all indexes
docker exec atlas-postgres psql -U atlas -d atlas -c "\di"

# Check constraints
docker exec atlas-postgres psql -U atlas -d atlas -c \
  "SELECT table_name, constraint_name, constraint_type 
   FROM information_schema.table_constraints 
   WHERE table_schema='public';"

# Check data types
docker exec atlas-postgres psql -U atlas -d atlas -c \
  "SELECT table_name, column_name, data_type 
   FROM information_schema.columns 
   WHERE table_schema='public' 
   ORDER BY table_name, ordinal_position;"
```

**Validation Checklist**:
- [ ] All 10 tables created
- [ ] All indexes created (especially on tenant_id, document_id)
- [ ] Soft delete columns present (deleted_at)
- [ ] Timestamp columns present (created_at, updated_at)
- [ ] UUID primary keys
- [ ] Foreign key constraints defined
- [ ] Unique constraints on multi-column fields

---

## PART 3: RUN TEST SUITE AGAINST POSTGRESQL

### Step 3.1: Update Test Configuration

```python
# Create tests/conftest.py override for PostgreSQL
# Set environment variable to use PostgreSQL instead of SQLite

export DATABASE_URL="postgresql+asyncpg://atlas:atlas@localhost:5432/atlas"
```

### Step 3.2: Run Unit Tests Against PostgreSQL

```bash
cd /path/to/ATLAS

# Run full test suite
python -m pytest tests/ -v \
  --cov=backend \
  --cov-report=html \
  --cov-report=term

# Run specific test modules
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_documents.py -v  
python -m pytest tests/test_cache.py -v
python -m pytest tests/test_retrieval.py -v
```

**Expected Results**:
- ✅ All tests should pass (or same failures as SQLite)
- ✅ Tests should use PostgreSQL instead of in-memory SQLite
- ✅ Connection pooling should work
- ✅ UUID handling should work
- ✅ JSON/ARRAY types should work
- ✅ Transaction isolation should work

**PostgreSQL-Specific Issues to Check**:
1. **Async Connection Handling**: Ensure all connections properly await
2. **Transaction Management**: Verify transactions commit/rollback correctly
3. **UUID Column Handling**: Check UUID primary keys work with asyncpg
4. **JSON Type Compatibility**: Verify JSON columns serialize/deserialize
5. **ARRAY Type Compatibility**: Check ARRAY(String) columns work
6. **Index Performance**: Query should use indexes efficiently
7. **Connection Pooling**: Verify connection pool not exhausted
8. **Prepared Statements**: Ensure asyncpg prepared statements work

**Troubleshooting**:
```bash
# If connection fails:
docker logs atlas-postgres

# If migrations incomplete:
docker exec atlas-api alembic upgrade head

# If schema mismatch:
docker exec atlas-api alembic downgrade base
docker exec atlas-api alembic upgrade head
```

---

## PART 4: REAL END-TO-END DOCUMENT FLOW

### Step 4.1: Register & Login

```bash
# 1. Register User
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@atlas.local",
    "password": "SecurePass123!",
    "full_name": "Test User"
  }'

# Expected: 201 Created, user_id returned

# 2. Login
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@atlas.local", 
    "password": "SecurePass123!"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"
```

**Validation Checklist**:
- [ ] User created in PostgreSQL
- [ ] Password hashed with PBKDF2
- [ ] JWT token returned with 24hr expiration
- [ ] Token can be decoded and validated

### Step 4.2: Create Tenant & Collection

```bash
# 1. Create Tenant (or get if user-owned)
TENANT_ID=$(curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Tenant"
  }' | jq -r '.id')

echo "Tenant ID: $TENANT_ID"

# 2. Create Collection
COLLECTION_ID=$(curl -X POST http://localhost:8000/api/v1/collections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"tenant_id\": \"$TENANT_ID\",
    \"name\": \"Test Documents\",
    \"description\": \"Integration test collection\"
  }" | jq -r '.id')

echo "Collection ID: $COLLECTION_ID"
```

### Step 4.3: Upload Document

```bash
# Create test document
cat > /tmp/test-doc.txt << 'EOF'
# Test Document for ATLAS Integration

This is a test document for the ATLAS RAG system.
It contains information about machine learning and artificial intelligence.

## Section 1: Machine Learning Basics

Machine Learning (ML) is a subset of Artificial Intelligence that enables 
systems to learn and improve from experience without being explicitly programmed.

Types of Machine Learning:
- Supervised Learning
- Unsupervised Learning
- Reinforcement Learning

## Section 2: Deep Learning

Deep Learning is a subset of Machine Learning using neural networks
with multiple layers (hence "deep").

Applications:
- Computer Vision
- Natural Language Processing
- Speech Recognition

## Section 3: Practical Applications

ML is used in:
1. Recommendation Systems
2. Fraud Detection
3. Image Recognition
4. Chatbots and Virtual Assistants
5. Autonomous Vehicles

This document contains knowledge that should be retrieved and ranked
by the ATLAS retrieval system.
EOF

# Upload to ATLAS
DOCUMENT_ID=$(curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/test-doc.txt" \
  -F "collection_id=$COLLECTION_ID" \
  -F "title=Test Document" | jq -r '.id')

echo "Document ID: $DOCUMENT_ID"
```

**Validation Checklist - Document Created**:
- [ ] Document record in PostgreSQL
- [ ] File uploaded to MinIO object storage
- [ ] Document status = PENDING
- [ ] Processing job created
- [ ] Kafka event published (check logs)

### Step 4.4: Monitor Document Processing

```bash
# Check document status
curl -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  http://localhost:8000/api/v1/documents/$DOCUMENT_ID | jq '.status'

# Monitor ingestion worker logs
docker logs -f atlas-worker-ingestion

# Expected output shows:
# - Document retrieved from PostgreSQL
# - File fetched from MinIO
# - Content parsed (TXT format)
# - Text chunked into segments
# - Embeddings generated
# - Vectors sent to Qdrant
# - Status updated to READY
```

**Processing Pipeline Validation**:

1. **PostgreSQL**: Document row marked as PROCESSING
2. **MinIO**: File accessible and readable
3. **Worker**: Kafka message consumed (check consumer lag)
4. **Parser**: Content extracted correctly
5. **Chunking**: Document split into semantic chunks (typically 300-500 tokens)
6. **Embedding**: Vector generated via sentence-transformers (384 dimensions)
7. **Qdrant**: Vectors stored with metadata (document_id, tenant_id, chunk_id)
8. **PostgreSQL**: Chunk rows created with embeddings
9. **Redis**: Cache invalidated for tenant
10. **Final**: Document status = READY in PostgreSQL

---

## PART 5: END-TO-END SEARCH VALIDATION

### Step 5.1: Test BM25 Lexical Search

```bash
QUERY="What is machine learning?"

curl -X POST http://localhost:8000/api/v1/search/bm25 \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$QUERY\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"top_k\": 5
  }" | jq '.'
```

**Validation Checklist - BM25**:
- [ ] Returns top 5 chunks by relevance score
- [ ] Scores represent TF-IDF ranking
- [ ] Results include source_document_id
- [ ] Results include chunk_position
- [ ] Confidence score between 0-1
- [ ] Query time < 500ms
- [ ] Correct chunks returned (Section 1)

### Step 5.2: Test Dense Vector Search

```bash
QUERY="machine learning types and applications"

curl -X POST http://localhost:8000/api/v1/search/dense \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$QUERY\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"top_k\": 5
  }" | jq '.'
```

**Validation Checklist - Dense Retrieval**:
- [ ] Query embedded via sentence-transformers
- [ ] Embedding is 384 dimensions
- [ ] Qdrant queried for nearest neighbors
- [ ] Top 5 results returned by cosine similarity
- [ ] Similarity scores between 0-1
- [ ] Query time < 1000ms
- [ ] Relevant chunks returned (Sections 1, 3)

### Step 5.3: Test Hybrid Retrieval (BM25 + Dense + RRF)

```bash
QUERY="AI applications in industry"

curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$QUERY\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"top_k\": 5,
    \"bm25_weight\": 0.4,
    \"dense_weight\": 0.6
  }" | jq '.'
```

**Validation Checklist - Hybrid Search**:
- [ ] Both BM25 and dense search executed
- [ ] Reciprocal Rank Fusion (RRF) combines rankings
- [ ] Weights properly balanced (0.4 + 0.6 = 1.0)
- [ ] Top 5 results returned
- [ ] Relevant to query (Sections 1, 3)
- [ ] Query time < 1500ms

### Step 5.4: Test Cache Performance

```bash
# First query (cold cache)
time curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"machine learning\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"top_k\": 5
  }" > /dev/null

# Identical query (warm cache)
time curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"machine learning\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"top_k\": 5
  }" > /dev/null
```

**Validation Checklist - Cache**:
- [ ] Cold cache: ~1000-1500ms
- [ ] Warm cache: ~100-300ms
- [ ] Cache hit rate visible in logs
- [ ] Redis keys follow tenant_id pattern
- [ ] Cache invalidated on document update

---

## PART 6: END-TO-END RAG PIPELINE

### Step 6.1: Execute RAG Query with LLM Integration

```bash
QUERY="What are the different types of machine learning?"

curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"question\": \"$QUERY\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"top_k\": 3,
    \"include_sources\": true,
    \"stream\": false
  }" | jq '.'
```

**Expected Response Schema**:
```json
{
  "answer": "Based on the provided documents...",
  "sources": [
    {
      "document_id": "...",
      "document_title": "Test Document",
      "chunk_id": "...",
      "content": "Types of Machine Learning: ...",
      "confidence": 0.95
    }
  ],
  "metadata": {
    "retrieval_latency_ms": 150,
    "llm_latency_ms": 2500,
    "total_latency_ms": 2650,
    "retrieved_chunk_count": 3,
    "used_cache": false
  }
}
```

**Validation Checklist - RAG**:
- [ ] Question processed correctly
- [ ] Retrieved relevant chunks from document
- [ ] Context properly formatted for LLM
- [ ] LLM provider called (mock or real based on config)
- [ ] Answer includes citations from sources
- [ ] Sources include document metadata
- [ ] Confidence scores realistic (0.7-1.0)
- [ ] Latency metrics captured
- [ ] No sensitive information in error responses
- [ ] Proper error handling if LLM unavailable

### Step 6.2: Test Streaming RAG Response

```bash
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"question\": \"Explain deep learning applications\",
    \"collection_id\": \"$COLLECTION_ID\",
    \"stream\": true
  }" \
  --no-buffer
```

**Validation Checklist - Streaming**:
- [ ] Response streams in real-time (Server-Sent Events or chunked)
- [ ] Each chunk contains partial answer
- [ ] Proper formatting for streaming
- [ ] Client can parse streamed response

---

## PART 7: MULTI-TENANT SECURITY TESTS

### Step 7.1: Create Second Tenant & User

```bash
# Register second user
TOKEN2=$(curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user2@atlas.local",
    "password": "SecurePass456!",
    "full_name": "User Two"
  }' | jq -r '.access_token')

TENANT2_ID=$(curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Authorization: Bearer $TOKEN2" \
  -H "Content-Type: application/json" \
  -d '{"name": "Tenant Two"}' | jq -r '.id')

COLLECTION2_ID=$(curl -X POST http://localhost:8000/api/v1/collections \
  -H "Authorization: Bearer $TOKEN2" \
  -H "Content-Type: application/json" \
  -d "{
    \"tenant_id\": \"$TENANT2_ID\",
    \"name\": \"Secret Documents\",
    \"description\": \"User 2 only\"
  }" | jq -r '.id')

# Upload secret document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN2" \
  -H "X-Tenant-ID: $TENANT2_ID" \
  -F "file=@/tmp/secret.txt" \
  -F "collection_id=$COLLECTION2_ID" \
  -F "title=Secret Document"
```

### Step 7.2: Attempt Cross-Tenant Access (Should Fail)

```bash
# Attempt 1: User 1 tries to access User 2's tenant
RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/v1/tenants/$TENANT2_ID \
  -H "Authorization: Bearer $TOKEN")

echo "Status code: $RESULT"  # Should be 403 or 401

# Attempt 2: User 1 tries to access User 2's collection
RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/v1/collections/$COLLECTION2_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID")

echo "Status code: $RESULT"  # Should be 403 or 404

# Attempt 3: User 1 tries to search User 2's documents
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"secret documents\",
    \"collection_id\": \"$COLLECTION2_ID\",
    \"top_k\": 10
  }"

# Should return empty results or error

# Attempt 4: User 1 tries to forge tenant_id header
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT2_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"steal secrets\",
    \"collection_id\": \"$COLLECTION2_ID\",
    \"top_k\": 10
  }"

# Should be rejected based on JWT token (which has original tenant_id)
```

**Validation Checklist - Multi-Tenant Isolation**:
- [ ] Cross-tenant document access rejected (403/404)
- [ ] Cross-tenant collection access rejected (403/404)
- [ ] Cross-tenant search returns no results
- [ ] Forged tenant_id header rejected
- [ ] JWT token contains correct tenant_id
- [ ] Database queries filtered by tenant_id
- [ ] Redis cache keys include tenant_id prefix
- [ ] MinIO object paths include tenant_id
- [ ] PostgreSQL queries enforce tenant_id filter
- [ ] No data leakage in error messages

---

## PART 8: DUPLICATE EVENT IDEMPOTENCY TEST

### Step 8.1: Publish Same Kafka Event Multiple Times

```bash
# Get processing job ID
JOB_ID=$(curl -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  http://localhost:8000/api/v1/documents/$DOCUMENT_ID/jobs | \
  jq -r '.jobs[0].id')

# Manually publish duplicate ingestion events
docker exec atlas-kafka kafka-console-producer.sh \
  --broker-list localhost:9092 \
  --topic document-ingestion << EOF
{"job_id": "$JOB_ID", "document_id": "$DOCUMENT_ID", "tenant_id": "$TENANT_ID"}
{"job_id": "$JOB_ID", "document_id": "$DOCUMENT_ID", "tenant_id": "$TENANT_ID"}
{"job_id": "$JOB_ID", "document_id": "$DOCUMENT_ID", "tenant_id": "$TENANT_ID"}
EOF

# Wait for processing
sleep 10

# Check chunk count
curl -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  http://localhost:8000/api/v1/documents/$DOCUMENT_ID/chunks | \
  jq '.total_chunks'
```

**Validation Checklist - Idempotency**:
- [ ] Chunk count same as before duplicates (no additional chunks)
- [ ] Vector count in Qdrant unchanged
- [ ] No duplicate rows in PostgreSQL chunks table
- [ ] Document status remains READY
- [ ] Processing job state consistent
- [ ] No error logs from duplicate processing
- [ ] Kafka offset tracked correctly (consumer committed offset advanced once per event)

**Implementation Check**:
```sql
-- Check for duplicates in chunks table
SELECT document_id, COUNT(*) as chunk_count,
       COUNT(DISTINCT chunk_number) as unique_chunks
FROM chunk
WHERE document_id = '<DOCUMENT_ID>'
GROUP BY document_id;
```

---

## PART 9: WORKER FAILURE RECOVERY TEST

### Step 9.1: Start Processing & Kill Worker

```bash
# Upload new document (will start processing)
DOCUMENT_ID_2=$(curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/large-doc.pdf" \
  -F "collection_id=$COLLECTION_ID" | jq -r '.id')

# Give worker time to start processing
sleep 3

# Kill worker while processing
docker kill atlas-worker-ingestion

# Verify message still in Kafka
docker exec atlas-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group atlas-ingestion \
  --describe

# Wait 10 seconds
sleep 10

# Restart worker
docker compose up -d worker-ingestion

# Monitor recovery
docker logs -f atlas-worker-ingestion
```

**Validation Checklist - Failure Recovery**:
- [ ] Kafka message not lost (offset not committed before failure)
- [ ] Processing resumes after worker restart
- [ ] Document status transitions correctly (PENDING → PROCESSING → READY)
- [ ] No duplicate chunks created after resume
- [ ] Final document state deterministic (READY or FAILED)
- [ ] Worker logs show message reprocessing
- [ ] No data corruption in PostgreSQL
- [ ] Qdrant vectors correct after recovery

**Delivery Guarantee Verification**:
- If using Kafka transactions: At-least-once guarantee
- If using offset commits: Manual offset management (verify offset not committed before processing complete)
- Check `/backend/workers/ingestion_worker.py` for offset commit strategy

---

## PART 10: REDIS FAILURE TEST

### Step 10.1: Stop Redis While API Running

```bash
# Current state: Redis is running
redis-cli -h localhost ping  # Returns PONG

# Make request to warm cache
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}' > /dev/null

# Stop Redis
docker stop atlas-redis

# Attempt normal operations
echo "Testing operations without Redis..."

# Test 1: Search without cache
RESULT=$(curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}' \
  -w "\n%{http_code}")

echo "$RESULT" | tail -1  # Should be 200, not 5xx

# Test 2: Authentication (should not use cache)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"testuser@atlas.local","password":"SecurePass123!"}'

# Test 3: Document retrieval (should work via PostgreSQL)
curl http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID"

# Check API logs for Redis failure handling
docker logs atlas-api 2>&1 | grep -i "redis"

# Restart Redis
docker start atlas-redis

# Verify recovery
redis-cli -h localhost ping

# Cache should work again
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}'
```

**Validation Checklist - Redis Failure**:
- [ ] API continues functioning without Redis
- [ ] Search operations degrade gracefully (bypass cache, hit Qdrant directly)
- [ ] Authentication does NOT bypass security (still checks JWT)
- [ ] No 5xx errors (graceful degradation, not catastrophic failure)
- [ ] Logs clearly show Redis unavailable
- [ ] Cache-dependent operations show warning logs
- [ ] API recovers after Redis restart
- [ ] Cache works again after recovery
- [ ] No sensitive stack traces exposed

---

## PART 11: QDRANT FAILURE TEST

### Step 11.1: Stop Qdrant During Retrieval

```bash
# Verify Qdrant is healthy
curl http://localhost:6333/health

# Stop Qdrant
docker stop atlas-qdrant

# Attempt dense search (requires Qdrant)
curl -X POST http://localhost:8000/api/v1/search/dense \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}'

# Attempt BM25 (does NOT require Qdrant)
curl -X POST http://localhost:8000/api/v1/search/bm25 \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}'

# Attempt hybrid (requires Qdrant)
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}'

# Check error response
docker logs atlas-api | grep -i qdrant

# Restart Qdrant
docker start atlas-qdrant

# Wait for health
sleep 5
curl http://localhost:6333/health

# Verify dense search works again
curl -X POST http://localhost:8000/api/v1/search/dense \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "collection_id": "'$COLLECTION_ID'"}'
```

**Validation Checklist - Qdrant Failure**:
- [ ] Dense search returns controlled error (503 or 500 with proper message)
- [ ] BM25 search continues working
- [ ] Hybrid search returns controlled error
- [ ] No stack traces exposed to client
- [ ] Logs clearly identify Qdrant unavailable
- [ ] No data corruption during failure
- [ ] Service recovers after Qdrant restart
- [ ] Dense search works after recovery

---

## PART 12: KAFKA FAILURE TEST

### Step 12.1: Stop Kafka & Test Document Ingestion

```bash
# Verify Kafka is healthy
docker exec atlas-kafka kafka-broker-api-versions.sh \
  --bootstrap-server localhost:9092

# Stop Kafka
docker stop atlas-kafka atlas-zookeeper

# Attempt to upload document
RESULT=$(curl -s -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/test2.txt" \
  -F "collection_id=$COLLECTION_ID" \
  -w "\n%{http_code}")

echo "$RESULT" | tail -1  # Should be 202 Accepted or similar

# Check if document queued
curl http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '.documents[].status'

# Wait and restart Kafka
sleep 5
docker start atlas-zookeeper
sleep 5
docker start atlas-kafka
sleep 10

# Verify processing starts
docker logs -f atlas-worker-ingestion | grep -i "processing"

# Verify document reaches READY
sleep 30
curl http://localhost:8000/api/v1/documents/$DOCUMENT_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" | jq '.status'
```

**Validation Checklist - Kafka Failure**:
- [ ] Document upload accepted even if Kafka unavailable
- [ ] Document status initially PENDING (queued locally)
- [ ] API behavior controlled (no 5xx errors)
- [ ] Message eventually processed when Kafka returns
- [ ] Document status transitions to READY correctly
- [ ] No data loss
- [ ] Processing resumes automatically after recovery
- [ ] Error handling logged appropriately

---

## PART 13: DOCUMENT SECURITY TESTS

### Step 13.1: Test Edge Cases & Malformed Files

```bash
# Test 1: Oversized file
dd if=/dev/zero of=/tmp/huge.bin bs=1M count=1000  # 1GB file
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/huge.bin" \
  -F "collection_id=$COLLECTION_ID" \
  -w "\n%{http_code}"

# Test 2: Unsupported file type
echo "Some binary data" | base64 > /tmp/random.xyz
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/random.xyz" \
  -F "collection_id=$COLLECTION_ID" \
  -w "\n%{http_code}"

# Test 3: Empty file
touch /tmp/empty.txt
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/empty.txt" \
  -F "collection_id=$COLLECTION_ID" \
  -w "\n%{http_code}"

# Test 4: Path traversal in filename
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/test.txt;filename=../../etc/passwd" \
  -F "collection_id=$COLLECTION_ID"

# Test 5: Duplicate file (same content checksum)
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/test-doc.txt" \
  -F "collection_id=$COLLECTION_ID" \
  -w "\n%{http_code}"
```

**Validation Checklist - File Handling**:
- [ ] Oversized file rejected (400/413)
- [ ] Unsupported type rejected (400)
- [ ] Empty file handled (accepted or rejected gracefully)
- [ ] Path traversal in filename not executed (file stored safely)
- [ ] Duplicate detection works via content checksum
- [ ] No arbitrary filesystem access
- [ ] MinIO storage path safe and isolated
- [ ] Proper HTTP status codes returned
- [ ] User-friendly error messages
- [ ] No internal path information leaked

---

## PART 14: API VALIDATION

### Step 14.1: Test All Endpoints & Response Codes

```bash
# Helper function
test_endpoint() {
  local method=$1
  local endpoint=$2
  local data=$3
  local expected_code=$4
  
  local result=$(curl -s -X "$method" "http://localhost:8000/api/v1$endpoint" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "Content-Type: application/json" \
    -d "$data" \
    -w "\n%{http_code}")
  
  local code=$(echo "$result" | tail -1)
  if [ "$code" = "$expected_code" ]; then
    echo "✅ $method $endpoint: $code"
  else
    echo "❌ $method $endpoint: Expected $expected_code, got $code"
  fi
}

# Auth endpoints
test_endpoint "POST" "/auth/register" '{"email":"test@test.com","password":"pass"}' "201"
test_endpoint "POST" "/auth/login" '{"email":"test@test.com","password":"wrong"}' "401"

# Tenant endpoints
test_endpoint "GET" "/tenants" "" "200"
test_endpoint "POST" "/tenants" '{"name":"New"}' "201"
test_endpoint "GET" "/tenants/$TENANT_ID" "" "200"

# Collection endpoints  
test_endpoint "GET" "/collections" "" "200"
test_endpoint "POST" "/collections" '{"name":"New","tenant_id":"'$TENANT_ID'"}' "201"
test_endpoint "GET" "/collections/$COLLECTION_ID" "" "200"
test_endpoint "GET" "/collections/invalid-id" "" "404"

# Document endpoints
test_endpoint "GET" "/documents" "" "200"
test_endpoint "GET" "/documents/$DOCUMENT_ID" "" "200"
test_endpoint "DELETE" "/documents/$DOCUMENT_ID" "" "204"
test_endpoint "GET" "/documents/invalid-id" "" "404"

# Search endpoints
test_endpoint "POST" "/search/bm25" '{"query":"test","collection_id":"'$COLLECTION_ID'"}' "200"
test_endpoint "POST" "/search/dense" '{"query":"test","collection_id":"'$COLLECTION_ID'"}' "200"
test_endpoint "POST" "/search/hybrid" '{"query":"test","collection_id":"'$COLLECTION_ID'"}' "200"

# RAG endpoint
test_endpoint "POST" "/rag/query" '{"question":"test","collection_id":"'$COLLECTION_ID'"}' "200"

# Health endpoints
test_endpoint "GET" "/health" "" "200"
test_endpoint "GET" "/ready" "" "200"
```

**Validation Checklist - HTTP Status Codes**:
- [ ] 200 OK for successful GET
- [ ] 201 Created for POST creating resource
- [ ] 204 No Content for DELETE
- [ ] 400 Bad Request for invalid input
- [ ] 401 Unauthorized for missing auth
- [ ] 403 Forbidden for cross-tenant access
- [ ] 404 Not Found for missing resource
- [ ] 413 Payload Too Large for oversized file
- [ ] 500 Internal Server Error for server failures
- [ ] Consistent error response schema

### Step 14.2: Test Pagination & Filtering

```bash
# Test pagination
curl -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  "http://localhost:8000/api/v1/documents?limit=10&offset=0" | jq '.total, .limit, .offset'

# Test filtering
curl -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  "http://localhost:8000/api/v1/documents?status=READY" | jq '.documents[].status'

# Test sorting
curl -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  "http://localhost:8000/api/v1/documents?sort=created_at&order=desc" | jq '.documents[0].created_at'
```

**Validation Checklist - Pagination**:
- [ ] Limit parameter respected
- [ ] Offset parameter works correctly
- [ ] Total count returned
- [ ] Default limits applied
- [ ] Max limit enforced (prevent DOS)

---

## PART 15: OBSERVABILITY VALIDATION

### Step 15.1: Check Health & Readiness Endpoints

```bash
# Health check
curl -s http://localhost:8000/health | jq '.services'

# Readiness
curl -s http://localhost:8000/ready | jq '.'

# Both should include status of database, cache, embedding, LLM
```

### Step 15.2: Verify Metrics Endpoint

```bash
# Prometheus metrics
curl -s http://localhost:8000/metrics | head -30

# Should include:
# - http_requests_total
# - http_request_duration_seconds
# - ingestion_documents_total
# - retrieval_latency_seconds
# - cache_hits_total
# - cache_misses_total
```

### Step 15.3: Prometheus Scraping

```bash
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[]'

# Should show:
# - API endpoint (localhost:8000/metrics)
# - Worker endpoint (if metrics exposed)
```

### Step 15.4: Grafana Dashboard

```bash
# Access Grafana
curl -s http://localhost:3000/api/datasources | jq '.'

# Should show Prometheus datasource configured

# Verify dashboards exist
curl -s http://localhost:3000/api/search | jq '.[] | .title'

# Expected dashboards:
# - ATLAS Overview
# - API Metrics
# - Ingestion Worker
# - Database Performance
# - Cache Performance
```

### Step 15.5: Structured Logging

```bash
# Check API logs for structured format
docker logs atlas-api 2>&1 | grep "request_id\|user_id\|latency_ms"

# Expected log format:
# {
#   "timestamp": "2024-10-03T...",
#   "level": "info",
#   "message": "Processing document",
#   "request_id": "uuid-...",
#   "tenant_id": "...",
#   "document_id": "...",
#   "duration_ms": 1234
# }

# Check worker logs
docker logs atlas-worker-ingestion 2>&1 | grep "event="
```

**Validation Checklist - Observability**:
- [ ] /health endpoint returns service status
- [ ] /ready endpoint returns 200 when ready
- [ ] Prometheus metrics exposed on /metrics
- [ ] Request latency measured and exposed
- [ ] Cache hit/miss rates tracked
- [ ] Document processing metrics captured
- [ ] Worker throughput metrics available
- [ ] Request tracing via request_id
- [ ] Structured logging in JSON format
- [ ] Grafana dashboards load with real data

---

## PART 16: FRONTEND SMOKE TEST

### Step 16.1: Access Frontend

```bash
# Open browser to http://localhost:5173
# OR test via curl

curl -s http://localhost:5173 | grep -o "<title>.*</title>"
```

### Step 16.2: Test User Flow

```bash
# In Selenium/Cypress or browser:
1. Load http://localhost:5173/login
2. Register new user (test@frontend.local / Pass123!)
3. Login with credentials
4. View dashboard
5. Create collection
6. Upload document
7. Wait for processing status
8. Execute search
9. View RAG response with citations
10. Logout
```

**Validation Checklist - Frontend**:
- [ ] Page loads without JS errors
- [ ] API calls use correct base URL
- [ ] Authentication token passed in headers
- [ ] Form validation works
- [ ] Error messages displayed
- [ ] Document upload progress shown
- [ ] Processing status updates live
- [ ] Search results load
- [ ] Citations properly displayed
- [ ] Responsive design works

---

## PART 17: SECURITY AUDIT

### Step 17.1: JWT Token Analysis

```bash
# Decode token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"testuser@atlas.local","password":"SecurePass123!"}' | jq -r '.access_token')

# Decode (manually via jwt.io or jq)
echo $TOKEN | cut -d. -f2 | base64 -d | jq '.'

# Validation checklist for JWT:
# - Contains user_id
# - Contains tenant_id
# - Contains exp (expiration - should be 24 hours)
# - Contains iat (issued at)
# - Uses HS256 algorithm
# - No sensitive data in payload (passwords, API keys)
```

### Step 17.2: Password Hashing

```bash
# Check password hashing in PostgreSQL
docker exec atlas-postgres psql -U atlas -d atlas << EOF
SELECT user_id, password_hash FROM user_account LIMIT 1;
EOF

# Validation:
# - Hash is PBKDF2-SHA256 format (should start with "$pbkdf2-sha256$")
# - Not stored in plaintext
# - Hash length > 100 characters
```

### Step 17.3: CORS Configuration

```bash
# Check CORS headers
curl -i -X OPTIONS http://localhost:8000/api/v1/health

# Validation:
# - Access-Control-Allow-Origin set appropriately (not * for production)
# - Access-Control-Allow-Methods defined
# - Access-Control-Allow-Credentials if needed
```

### Step 17.4: SQL Injection Test

```bash
# Attempt SQL injection
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"'; DROP TABLE documents; --\",
    \"collection_id\": \"$COLLECTION_ID\"
  }"

# Verify:
# - No error exposing SQL
# - Documents table still exists
# - Parameterized queries used (check source code)
```

### Step 17.5: File Upload Security

```bash
# Test malicious filename
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@/tmp/test.txt;filename=../../etc/passwd" \
  -F "collection_id=$COLLECTION_ID"

# Verify:
# - Filename sanitized
# - File stored in tenant-specific MinIO path
# - No filesystem traversal possible
```

### Step 17.6: Tenant Isolation in Storage

```bash
# Check MinIO structure
docker exec atlas-minio mc ls minio/atlas-documents

# Should show:
# /tenant-<UUID>/documents/<document-id>
# Not accessible to other tenants
```

### Step 17.7: Redis Cache Security

```bash
# Check cache key pattern
redis-cli -h localhost keys "rag:cache:*" | head -5

# Validation:
# - Keys include tenant_id
# - No sensitive data in values (only hash references)
# - Proper TTL set
```

**Validation Checklist - Security**:
- [ ] JWT tokens contain no sensitive data
- [ ] Passwords hashed with PBKDF2 (100k iterations minimum)
- [ ] SQL queries parameterized (no string concatenation)
- [ ] File uploads sanitized and isolated
- [ ] CORS configured appropriately
- [ ] Tenant isolation enforced in database queries
- [ ] Cache keys include tenant_id
- [ ] Object storage paths include tenant_id
- [ ] No sensitive stack traces exposed
- [ ] Proper HTTP security headers set

---

## PART 18: COVERAGE ANALYSIS

### Step 18.1: Generate Coverage Report

```bash
cd /path/to/ATLAS

# Run tests with coverage
python -m pytest tests/ \
  --cov=backend \
  --cov-report=html \
  --cov-report=json

# Extract coverage by module
python -m coverage json -o coverage.json

# Parse and report
python << 'EOF'
import json
with open('coverage.json') as f:
  data = json.load(f)
  
total_coverage = data['totals']['percent_covered']
print(f"Total Coverage: {total_coverage}%")

print("\nCritical Path Coverage:")
for module in ['backend/services/documents.py', 
               'backend/services/retrieval.py',
               'backend/services/rag_pipeline.py']:
  if module in data['files']:
    coverage = data['files'][module]['summary']['percent_covered']
    print(f"  {module}: {coverage}%")
EOF
```

### Step 18.2: Identify Coverage Gaps

```bash
# View uncovered lines
coverage report --skip-covered --skip-empty

# Generate HTML report
coverage html

# Key metrics:
# - Unit test coverage: Target 60-70% (not critical paths)
# - Integration test coverage: 40-50% (focus on E2E)
# - Critical path coverage: 80-90% (tenant isolation, ingestion, retrieval, RAG)
```

---

## PART 19: FINAL REPORT COMPILATION

After completing all tests, compile findings into:

### PHASE_3_VALIDATION_REPORT.md

This should include:

```markdown
# ATLAS Phase 3: Integration & Infrastructure Validation Report

## Test Environment
- Docker Desktop: [Version]
- PostgreSQL: 16-alpine
- Redis: 7-alpine
- Python: 3.13.9
- Date: [Today]

## Service Status
| Service | Status | Health Check | Details |
|---------|--------|-----|---------|
| PostgreSQL | PASS | ✅ | Migration successful, schema valid |
| Redis | PASS | ✅ | Connected, persistence enabled |
| Kafka | PASS | ✅ | Broker responding, topics created |
| Qdrant | PASS | ✅ | Health check 200, collections created |
| MinIO | PASS | ✅ | Bucket created, TLS ready |
| API | PASS | ✅ | All endpoints responding |
| Worker | PASS | ✅ | Consuming Kafka messages |
| Frontend | PASS | ✅ | Loading, API connected |
| Prometheus | PASS | ✅ | Scraping endpoints |
| Grafana | PASS | ✅ | Dashboards loaded |

## Integration Test Results

### Document Ingestion Pipeline
- Upload: PASS
- Storage: PASS
- Queue: PASS
- Processing: PASS
- Indexing: PASS
- Status Update: PASS

### Search & Retrieval
- BM25 Search: PASS
- Dense Retrieval: PASS
- Hybrid Search: PASS
- Caching: PASS
- Performance: PASS (avg 150ms)

### RAG Pipeline
- Question Processing: PASS
- Context Retrieval: PASS
- LLM Integration: PASS
- Citation Formatting: PASS
- Response Schema: PASS

### Multi-Tenant Security
- Tenant Isolation: PASS (8/8 attempts blocked)
- Data Access Control: PASS
- Forged Headers Rejected: PASS
- Cross-tenant Query: PASS (returned 0 results)

### Failure Recovery
- Worker Restart: PASS (message reprocessed)
- Idempotency: PASS (no duplicates)
- Redis Failure: PASS (graceful degradation)
- Qdrant Failure: PASS (controlled error)
- Kafka Failure: PASS (message queued)

### File Security
- Oversized Files: PASS (rejected)
- Invalid Types: PASS (rejected)
- Path Traversal: PASS (prevented)
- Duplicate Detection: PASS

### API Validation
- HTTP Status Codes: PASS (all correct)
- Error Responses: PASS (consistent schema)
- Pagination: PASS
- Filtering: PASS
- Authentication: PASS

### Observability
- Health Endpoints: PASS
- Metrics Endpoint: PASS
- Prometheus Scraping: PASS
- Grafana Dashboards: PASS
- Structured Logging: PASS

## Coverage Analysis

Total Coverage: 39% (focused on critical paths)

Critical Path Coverage:
- Authentication: 82%
- Documents: 62%
- Retrieval: 36%
- Cache: 66%

## Defects Found & Fixed

1. [Defect 1] - [Status: FIXED]
2. [Defect 2] - [Status: FIXED]

## Known Limitations

1. Cross-encoder reranking model not available in test environment
2. External LLM provider requires API key (mocked in tests)
3. OTLP tracing not validated (setup only)

## Unverified Components

- Load testing (single-user verified, multi-user not tested)
- TLS/HTTPS configuration (development only)
- Kubernetes deployment (Docker Compose only)
- Database failover (single instance tested)
- Multi-region setup (single region only)

## Recommendations

1. **Before Production**:
   - [ ] Complete load testing (1000+ concurrent users)
   - [ ] Setup production TLS certificates
   - [ ] Enable database replication
   - [ ] Configure backup/restore procedures
   - [ ] Perform penetration testing

2. **Monitoring**:
   - [ ] Deploy APM (DataDog, New Relic, or similar)
   - [ ] Setup alerting for critical metrics
   - [ ] Configure log aggregation (ELK, Loki)
   - [ ] Enable distributed tracing (Jaeger)

3. **Security**:
   - [ ] Rotate secrets regularly
   - [ ] Enable audit logging
   - [ ] Configure WAF rules
   - [ ] Implement rate limiting
   - [ ] Setup DDoS protection

## Sign-Off

**Validation Status**: ✅ PASSED (with known limitations)  
**Production Ready**: ✅ YES (for initial deployment)  
**Recommended Actions**: See recommendations above

**Date**: [Date]  
**Validator**: [Name]  
```

---

## EXECUTION CHECKLIST

- [ ] Part 1: Infrastructure Setup
  - [ ] Docker images built
  - [ ] Stack running
  - [ ] All services healthy
  - [ ] Connectivity validated

- [ ] Part 2: Database Validation
  - [ ] Migrations successful
  - [ ] Schema verified
  - [ ] Indexes created
  - [ ] Constraints defined

- [ ] Part 3: Unit Tests
  - [ ] All tests pass against PostgreSQL
  - [ ] No connection pool issues
  - [ ] UUID handling correct
  - [ ] Transaction management works

- [ ] Part 4: Document Flow
  - [ ] Register/login works
  - [ ] Document uploaded
  - [ ] File in MinIO
  - [ ] Worker processing
  - [ ] Status → READY

- [ ] Part 5: Search
  - [ ] BM25 results relevant
  - [ ] Dense retrieval scores high
  - [ ] Hybrid combines correctly
  - [ ] Cache improves latency

- [ ] Part 6: RAG
  - [ ] Question processed
  - [ ] Context retrieved
  - [ ] LLM called
  - [ ] Citations included

- [ ] Part 7: Multi-Tenant
  - [ ] Cross-tenant access blocked (8/8)
  - [ ] Forged headers rejected
  - [ ] Data isolated

- [ ] Part 8: Idempotency
  - [ ] Duplicates handled
  - [ ] No data corruption
  - [ ] Status consistent

- [ ] Part 9: Worker Recovery
  - [ ] Messages not lost
  - [ ] Processing resumes
  - [ ] Final state deterministic

- [ ] Part 10: Redis Failure
  - [ ] Graceful degradation
  - [ ] Security maintained
  - [ ] Recovery works

- [ ] Part 11: Qdrant Failure
  - [ ] Controlled error
  - [ ] BM25 still works
  - [ ] Recovery successful

- [ ] Part 12: Kafka Failure
  - [ ] Document queued
  - [ ] Processing eventually succeeds
  - [ ] No data loss

- [ ] Part 13: File Security
  - [ ] Oversized rejected
  - [ ] Invalid types rejected
  - [ ] Path traversal prevented
  - [ ] Duplicates detected

- [ ] Part 14: API Validation
  - [ ] Status codes correct
  - [ ] Pagination works
  - [ ] Filtering works
  - [ ] Error schema consistent

- [ ] Part 15: Observability
  - [ ] Health endpoints work
  - [ ] Metrics exposed
  - [ ] Prometheus scrapes
  - [ ] Grafana loads
  - [ ] Logs structured

- [ ] Part 16: Frontend
  - [ ] Loads without errors
  - [ ] User flow works
  - [ ] Connected to API

- [ ] Part 17: Security
  - [ ] JWT tokens validated
  - [ ] Passwords hashed
  - [ ] SQL injection prevented
  - [ ] File upload safe
  - [ ] Tenant isolation enforced

- [ ] Part 18: Coverage
  - [ ] Report generated
  - [ ] Critical paths identified
  - [ ] Gaps documented

- [ ] Part 19: Report
  - [ ] Comprehensive report created
  - [ ] All results documented
  - [ ] Recommendations provided

---

## NEXT STEPS

After completing Phase 3 validation:

1. **Fix Defects**: Address any FAIL results before deployment
2. **Performance Tuning**: Optimize slow queries or endpoints
3. **Load Testing**: Test with realistic concurrent users
4. **Production Deployment**: Follow deployment checklist
5. **Monitoring Setup**: Enable all observability
6. **Team Training**: Ensure team understands operational procedures

---

## APPENDIX A: Required Tools

```bash
# Install test tools if needed
pip install pytest pytest-asyncio pytest-cov
pip install redis
apt-get install postgresql-client  # For psql command
brew install postgresql-client     # For macOS
```

## APPENDIX B: Environment Variables

```bash
# .env for local testing
DATABASE_URL=postgresql+asyncpg://atlas:atlas@localhost:5432/atlas
REDIS_URL=redis://localhost:6379/0
KAFKA_BROKERS=localhost:9092
QDRANT_URL=http://localhost:6333
STORAGE_URL=http://localhost:9000
LLM_API_KEY=test-key-for-development
```

## APPENDIX C: Key Metrics to Track

- Document ingestion throughput (docs/second)
- Average latency for BM25 search (ms)
- Average latency for dense search (ms)
- Cache hit rate (%)
- Processing job success rate (%)
- API endpoint average latency (ms)
- Worker message processing rate (msgs/second)
- Error rate by endpoint (%)

