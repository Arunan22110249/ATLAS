# CONTRIBUTING TO ATLAS

Thank you for your interest in contributing to ATLAS! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Setup](#development-setup)
4. [Coding Standards](#coding-standards)
5. [Testing](#testing)
6. [Submitting Changes](#submitting-changes)
7. [Reporting Issues](#reporting-issues)
8. [Project Structure](#project-structure)
9. [Architecture Decisions](#architecture-decisions)

---

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors. Please:

- Be respectful and professional
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Report harassment or violations via email (if applicable)

---

## Getting Started

### Prerequisites

- Python 3.13+
- Node.js 18+ (for frontend)
- Docker & Docker Compose (for full stack)
- Git

### Quick Setup

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/atlas.git
   cd atlas
   ```
3. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Follow development setup** (see next section)

---

## Development Setup

### Backend Setup

1. **Create Python virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Add: pytest, black, ruff, mypy
   ```

3. **Set up environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your local configuration
   ```

4. **Run tests**:
   ```bash
   pytest tests/ -v
   ```

5. **Start backend** (requires services):
   ```bash
   # Option 1: Full Docker stack
   docker-compose up -d
   
   # Option 2: Backend only (requires external services)
   python -m backend.main
   ```

### Frontend Setup

1. **Install dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Start development server**:
   ```bash
   npm run dev
   ```

3. **Access**: Open `http://localhost:5173` (Vite default port)

### Full Stack Setup (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Run tests against running stack
pytest tests/ -v --integration

# Stop all services
docker-compose down
```

---

## Coding Standards

### Python Code Style

We follow PEP 8 with additional standards:

- **Formatter**: Black
- **Linter**: Ruff
- **Type Checker**: mypy (annotations encouraged)

```bash
# Format code
black backend/ tests/

# Check linting
ruff check backend/ tests/

# Type check
mypy backend/
```

### Naming Conventions

- **Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`
- **Async functions**: Prefix with `async def`

```python
# ✅ Good
async def get_document_by_id(doc_id: UUID) -> Optional[Document]:
    """Retrieve document by ID, filtering soft-deleted documents."""
    query = select(Document).where(
        (Document.id == doc_id) and
        (Document.status != DocumentStatus.DELETED)
    )
    return await session.scalar(query)

# ❌ Bad
def GetDocumentByID(docId):
    # No async, no type hints, no docstring
    return query
```

### Docstrings

All public functions must have docstrings:

```python
def hash_password(password: str) -> str:
    """
    Hash password using PBKDF2-SHA256.
    
    Args:
        password: Plain text password (minimum 8 characters)
    
    Returns:
        Hashed password in format: {salt}${hash_key}
    
    Raises:
        ValueError: If password is empty or too short
    
    Example:
        >>> hashed = hash_password("my-secure-password")
        >>> len(hashed.split("$")) == 2
        True
    """
    ...
```

### Async/Await Best Practices

- Always use `async`/`await` for I/O operations
- Don't use blocking libraries (e.g., `requests`; use `httpx` instead)
- Ensure all database operations use async session
- Use `asyncio.gather()` for parallel operations

```python
# ✅ Good - Async all the way
async def process_documents(docs: list[Document]):
    tasks = [_embed_document(doc) for doc in docs]
    results = await asyncio.gather(*tasks)
    return results

# ❌ Bad - Blocking call in async context
async def process_documents(docs: list[Document]):
    for doc in docs:
        response = requests.get(...)  # BLOCKS!
        ...
```

### Multi-Tenancy Enforcement

**Every database query must filter by tenant_id**:

```python
# ✅ Good - Tenant isolation enforced
async def get_documents(session: AsyncSession, tenant_id: UUID) -> list[Document]:
    query = select(Document).where(
        (Document.tenant_id == tenant_id) and
        (Document.status != DocumentStatus.DELETED)
    )
    return await session.scalars(query).all()

# ❌ Bad - Missing tenant filter
async def get_documents(session: AsyncSession) -> list[Document]:
    query = select(Document)  # Returns ALL documents!
    return await session.scalars(query).all()
```

### Caching & Keys

Cache keys must include tenant_id:

```python
# ✅ Good - Tenant isolation
cache_key = f"rag:cache:{tenant_id}:{query_hash}"

# ❌ Bad - Cross-tenant leakage
cache_key = f"rag:cache:{query_hash}"
```

### Error Handling

- Catch specific exceptions, not bare `except:`
- Log errors with context (user_id, tenant_id, operation)
- Return meaningful error messages to clients
- Use HTTP status codes correctly

```python
# ✅ Good
try:
    document = await get_document(session, doc_id, tenant_id)
except DocumentNotFoundError as e:
    logger.warning(f"Document not found: {doc_id}", 
                   extra={"tenant_id": str(tenant_id)})
    raise HTTPException(status_code=404, detail="Document not found")
except Exception as e:
    logger.error(f"Unexpected error retrieving document: {e}",
                 extra={"doc_id": str(doc_id), "tenant_id": str(tenant_id)})
    raise HTTPException(status_code=500, detail="Internal server error")

# ❌ Bad
except:
    raise  # No context, no logging
```

### TypeScript/JavaScript

- **Formatter**: Prettier
- **Linter**: ESLint
- **Framework**: React with TypeScript

```bash
cd frontend
npm run lint    # ESLint check
npm run format  # Prettier format
npm run type-check  # TypeScript check
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest tests/ --cov=backend --cov-report=html

# Run with specific marker
pytest tests/ -m "not integration" -v
```

### Writing Tests

Use pytest with async support:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_get_document_not_found(session: AsyncSession, tenant_id: UUID):
    """Test retrieving non-existent document returns 404."""
    doc_id = uuid.uuid4()
    
    with pytest.raises(DocumentNotFoundError):
        await get_document(session, doc_id, tenant_id)

@pytest.mark.asyncio
async def test_multi_tenant_isolation(session: AsyncSession):
    """Ensure documents from one tenant are invisible to another."""
    # Create two tenants
    tenant1 = Tenant(id=uuid.uuid4(), name="Tenant 1")
    tenant2 = Tenant(id=uuid.uuid4(), name="Tenant 2")
    
    # Add documents to tenant1
    doc1 = Document(id=uuid.uuid4(), tenant_id=tenant1.id, filename="doc.pdf")
    
    # Query tenant2 should NOT return doc1
    docs = await get_documents(session, tenant2.id)
    assert len(docs) == 0
    assert all(d.tenant_id == tenant2.id for d in docs)
```

### Test Coverage

- Target: 70%+ coverage of critical paths (auth, cache, documents, retrieval)
- Integration tests designed to run in Docker environment
- Mock external services (Kafka, Qdrant, LLM) in unit tests

---

## Submitting Changes

### Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/add-new-feature
   ```

2. **Make changes** following coding standards
3. **Add/update tests** for your changes
4. **Run quality checks**:
   ```bash
   black backend/ tests/
   ruff check backend/ tests/
   mypy backend/
   pytest tests/ -v
   ```

5. **Commit with clear messages**:
   ```bash
   git commit -m "feat: add new feature

   - Description of what was added
   - Why this change was necessary
   - Any breaking changes or migration notes
   
   Closes #123"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/add-new-feature
   ```

7. **Create Pull Request** on GitHub

### Pull Request Checklist

- [ ] Branch name follows `feature/`, `bugfix/`, or `docs/` convention
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Code formatted (`black`, `ruff`)
- [ ] Type hints included (`mypy` passes)
- [ ] Docstrings added for public functions
- [ ] Tests added for new functionality
- [ ] Multi-tenancy isolation verified (if accessing data)
- [ ] No secrets or credentials committed
- [ ] Commit messages are clear and descriptive
- [ ] PR description explains what and why

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

**Example**:
```
feat: implement hybrid search with RRF scoring

- Added reciprocal rank fusion algorithm
- Combined dense and BM25 results
- Verified tenant isolation in hybrid retrieval
- Covers edge cases: empty results, tie-breaking

Closes #42
```

---

## Reporting Issues

### Bug Reports

Include:
1. **Title**: Clear, specific description
2. **Environment**: OS, Python version, setup method
3. **Steps to reproduce**: Exact steps to trigger the bug
4. **Expected behavior**: What should happen
5. **Actual behavior**: What actually happened
6. **Error message**: Full traceback or error log
7. **Screenshots**: If UI-related

**Example**:
```markdown
## Title
Rate limiting returns 429 for legitimate requests

## Environment
- OS: macOS 13.1
- Python: 3.13.9
- Setup: docker-compose

## Steps to Reproduce
1. Start backend: `docker-compose up`
2. Run integration tests: `pytest tests/integration_tests.py`
3. Observe failure on 10th request

## Expected
All 20 requests should succeed

## Actual
Request 10 returns 429 Too Many Requests

## Error Log
```
rate_limit_middleware.py:42: Too many requests for user xyz
```
```

### Feature Requests

Include:
1. **Use case**: Why this feature is needed
2. **Proposed solution**: How it might work
3. **Alternatives**: Other approaches considered
4. **Additional context**: Relevant information

---

## Project Structure

```
atlas/
├── backend/                           # FastAPI application
│   ├── __init__.py
│   ├── main.py                       # Entry point, route definitions
│   ├── config.py                     # Configuration management
│   ├── database.py                   # Database connection pooling
│   ├── models.py                     # SQLAlchemy ORM models
│   ├── schemas.py                    # Pydantic request/response schemas
│   ├── middleware.py                 # Rate limiting, CORS, auth
│   ├── services/                     # Business logic
│   │   ├── auth.py                   # Authentication, JWT, password hashing
│   │   ├── documents.py              # Document CRUD, lifecycle
│   │   ├── collections.py            # Collection management
│   │   ├── cache.py                  # Redis semantic cache
│   │   ├── retrieval.py              # BM25, dense, hybrid search
│   │   ├── embedding.py              # Embedding generation
│   │   ├── document_parser.py        # File parsing, chunking
│   │   ├── llm.py                    # LLM integration (OpenAI, Azure)
│   │   ├── rag_pipeline.py           # RAG query, generation, citations
│   │   └── evaluation.py             # Evaluation metrics
│   └── workers/                      # Async workers
│       └── ingestion_worker.py       # Kafka consumer, document processing
├── frontend/                         # React/TypeScript application
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── tests/                            # Test suite
│   ├── conftest.py                   # Shared pytest fixtures
│   ├── test_auth.py
│   ├── test_cache.py
│   ├── test_documents.py
│   ├── test_retrieval.py
│   └── integration_tests.py
├── infrastructure/                   # Deployment configs
│   ├── kubernetes/                   # K8s manifests
│   ├── terraform/                    # Terraform IaC modules
│   └── docker/                       # Docker build contexts
├── alembic/                          # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
├── docs/                             # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── SETUP.md
│   └── DEPLOYMENT.md
├── docker-compose.yml                # Local development stack
├── Dockerfile.backend
├── Dockerfile.frontend
├── requirements.txt                  # Python dependencies
├── requirements-dev.txt              # Dev dependencies (lint, test, type-check)
├── package.json                      # Node dependencies
├── README.md                         # Main readme
├── SECURITY.md                       # Security model & guidelines
├── CONTRIBUTING.md                   # This file
├── LICENSE                           # Open source license
├── .env.example                      # Example environment variables
├── .gitignore                        # Git ignore patterns
└── .github/                          # GitHub automation
    ├── workflows/
    │   ├── test.yml
    │   ├── lint.yml
    │   └── deploy.yml
    └── issue_templates/
```

---

## Architecture Decisions

### Why async/await everywhere?

ATLAS is designed for high-concurrency I/O operations (database queries, HTTP calls, cache access). Async/await allows handling thousands of concurrent requests with minimal resource usage.

- **Trade-off**: More complex than blocking code, requires async-aware libraries
- **Benefit**: Scalable to large numbers of concurrent users
- **Enforcement**: Code review rejects blocking calls in async context

### Why SQLAlchemy ORM?

- **SQL Injection Prevention**: All queries parameterized
- **Multi-Tenancy**: Declarative model with automatic filtering
- **Type Safety**: Models define schema and types
- **Relationships**: Foreign keys, lazy/eager loading
- **Migrations**: Alembic tracks schema changes

### Why Redis for caching?

- **Performance**: In-memory, nanosecond latency
- **TTL Support**: Automatic cache expiration
- **Tenant Isolation**: Key prefixes prevent cross-tenant access
- **Monitoring**: Built-in stats and metrics
- **Reliability**: Replication and persistence options

### Why Kafka for ingestion?

- **Scalability**: Handle thousands of documents concurrently
- **Fault Tolerance**: Dead-letter queue for failed documents
- **Decoupling**: API doesn't wait for processing
- **Replay**: Can reprocess failed messages
- **Ordering**: Per-partition message ordering

### Why Qdrant for vectors?

- **Performance**: Optimized vector similarity search
- **Filtering**: Scalar and vector filters (tenant_id filtering)
- **Replication**: High availability options
- **Monitoring**: Built-in metrics and logs
- **Multi-language**: SDKs for Python, JavaScript, Go, etc.

---

## Getting Help

- **Issues**: Search existing issues before creating new ones
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check `docs/` folder for detailed guides
- **Chat**: (If applicable, provide Discord, Slack, etc.)

---

## Licensing

By contributing to ATLAS, you agree that your contributions will be licensed under the same license as the project (specified in LICENSE file).

---

**Last Updated**: 2025-01-14
**Version**: 1.0

