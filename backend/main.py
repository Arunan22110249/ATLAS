"""
Main FastAPI application for ATLAS.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import close_db, get_session, init_db
from backend.models import DocumentStatus
from backend.schemas import (
    CollectionCreateRequest,
    CollectionResponse,
    DocumentResponse,
    DocumentUploadResponse,
    HealthCheckResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    SearchRequest,
    SearchResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from backend.services import auth, documents
from backend.services.cache import SemanticCache
from backend.services.embedding import EmbeddingService
from backend.services.llm import LLMService
from backend.services.rag_pipeline import RAGPipeline

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

settings = get_settings()

# Global services
embedding_service: EmbeddingService = None
llm_service: LLMService = None
rag_pipeline: RAGPipeline = None
semantic_cache: SemanticCache = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global embedding_service, llm_service, rag_pipeline, semantic_cache
    
    # Startup
    logger.info("Starting ATLAS application")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Initialize services
        embedding_service = EmbeddingService(settings.embedding_model)
        llm_service = LLMService(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        
        # Initialize cache
        semantic_cache = SemanticCache(
            settings.redis_url,
            settings.semantic_cache_ttl_seconds,
        )
        await semantic_cache.connect()
        
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down ATLAS application")
    try:
        await semantic_cache.disconnect()
        await close_db()
        logger.info("Cleanup complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multi-Tenant Enterprise RAG & Knowledge Intelligence Platform",
    lifespan=lifespan,
)

# CORS
if settings.cors_origins != "*":
    origins = settings.cors_origins.split(",")
else:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()


# Dependency: Get current user
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
):
    """Extract and validate JWT token."""
    token = credentials.credentials
    payload = auth.decode_jwt_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    
    # Safely parse UUIDs from token
    try:
        user_id = uuid.UUID(payload.get("sub"))
        tenant_id = uuid.UUID(payload.get("tenant_id"))
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid UUID in token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
        )
    
    user = await auth.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    # Verify user's tenant matches token tenant (prevents token tampering)
    if user.tenant_id != tenant_id:
        logger.warning(f"Tenant mismatch for user {user_id}: {user.tenant_id} != {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    
    return {"user_id": user_id, "tenant_id": tenant_id, "user": user}


# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.post("/api/v1/auth/register", response_model=TokenResponse)
async def register(
    request: UserRegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user with tenant."""
    user, error = await auth.register_user(session, request)
    
    if error:
        logger.warning(f"Registration failed: {error}")
        raise HTTPException(status_code=400, detail=error)
    
    token, expires_in = auth.create_jwt_token(user.id, user.tenant_id)
    logger.info(f"User registered: {user.email}")
    
    return TokenResponse(access_token=token, expires_in=expires_in)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(
    request: UserLoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """Login user."""
    user, error = await auth.authenticate_user(session, request.email, request.password)
    
    if error:
        logger.warning(f"Login failed for {request.email}: {error}")
        raise HTTPException(status_code=401, detail=error)
    
    token, expires_in = auth.create_jwt_token(user.id, user.tenant_id)
    logger.info(f"User logged in: {user.email}")
    
    return TokenResponse(access_token=token, expires_in=expires_in)


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
):
    """Get current user profile."""
    return UserResponse.model_validate(current_user["user"])


# ============================================================================
# COLLECTION ROUTES
# ============================================================================

@app.post("/api/v1/collections", response_model=CollectionResponse)
async def create_collection(
    request: CollectionCreateRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new collection."""
    from backend.models import Collection
    
    collection = Collection(
        tenant_id=current_user["tenant_id"],
        name=request.name,
        description=request.description,
        metadata=request.metadata or {},
    )
    session.add(collection)
    await session.commit()
    
    logger.info(f"Collection created: {collection.name}")
    return CollectionResponse.model_validate(collection)


@app.get("/api/v1/collections", response_model=list[CollectionResponse])
async def list_collections(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List collections in tenant."""
    from sqlalchemy import select

    from backend.models import Collection
    
    result = await session.execute(
        select(Collection).where(Collection.tenant_id == current_user["tenant_id"])
    )
    collections = result.scalars().all()
    
    return [CollectionResponse.model_validate(c) for c in collections]


# ============================================================================
# DOCUMENT ROUTES
# ============================================================================

@app.post("/api/v1/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection_id: str = Query(None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Upload a document."""
    try:
        # Read file
        content = await file.read()
        
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")
        
        # Check size
        if len(content) > settings.max_document_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {settings.max_document_size_mb}MB)",
            )
        
        # Calculate checksum
        checksum = documents.calculate_checksum(content)
        
        # Check duplicate
        dup = await documents.check_duplicate_document(
            session,
            current_user["tenant_id"],
            checksum,
        )
        if dup:
            logger.warning(f"Duplicate document upload: {file.filename}")
            raise HTTPException(status_code=409, detail="Document already uploaded")
        
        # Create document
        doc_id = str(uuid.uuid4())
        storage_path = f"{current_user['tenant_id']}/{doc_id}/{file.filename}"
        
        collection_uuid = None
        if collection_id:
            collection_uuid = uuid.UUID(collection_id)
            # Validate collection belongs to current tenant (tenant isolation)
            from backend.models import Collection
            result = await session.execute(
                select(Collection).where(
                    (Collection.id == collection_uuid) & 
                    (Collection.tenant_id == current_user["tenant_id"])
                )
            )
            if not result.scalars().first():
                logger.warning(f"Tenant {current_user['tenant_id']} attempted to access collection {collection_id}")
                raise HTTPException(status_code=403, detail="Collection not found or access denied")
        
        doc = await documents.create_document(
            session,
            current_user["tenant_id"],
            doc_id,
            file.filename,
            file.content_type or "application/octet-stream",
            len(content),
            checksum,
            storage_path,
            collection_uuid,
        )
        
        await session.commit()
        
        # TODO: Upload to MinIO (would be done in workers)
        # TODO: Emit Kafka event for processing
        
        logger.info(f"Document uploaded: {file.filename} ({doc.id})")
        
        return DocumentUploadResponse(
            document_id=doc.id,
            filename=file.filename,
            status=DocumentStatus.UPLOADED.value,
            message="Document queued for processing",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed")


@app.get("/api/v1/documents", response_model=dict)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List documents in tenant."""
    docs, total = await documents.get_documents(
        session,
        current_user["tenant_id"],
        skip=skip,
        limit=limit,
    )
    
    return {
        "documents": [DocumentResponse.model_validate(d) for d in docs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@app.get("/api/v1/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get document details."""
    doc = await documents.get_document_by_id(
        session,
        uuid.UUID(document_id),
        current_user["tenant_id"],
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse.model_validate(doc)


@app.delete("/api/v1/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a document."""
    doc = await documents.delete_document(
        session,
        uuid.UUID(document_id),
        current_user["tenant_id"],
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    await session.commit()
    logger.info(f"Document deleted: {document_id}")
    
    return {"message": "Document deleted"}


# ============================================================================
# SEARCH ROUTES
# ============================================================================

@app.post("/api/v1/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Search documents."""
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        search_start = datetime.utcnow()
        results = await rag_pipeline.retriever.retrieve(
            request.query,
            str(current_user["tenant_id"]),
            request.top_k,
            request.filters,
        )
        search_time_ms = (datetime.utcnow() - search_start).total_seconds() * 1000
        
        return SearchResponse(
            results=[
                {
                    "chunk_id": r.chunk_id,
                    "document_id": r.document_id,
                    "document_name": r.metadata.get("source_filename", "Unknown"),
                    "document_version": r.metadata.get("document_version", 1),
                    "content": r.content,
                    "page_number": r.metadata.get("page_number"),
                    "section": r.metadata.get("section"),
                    "score": r.score,
                    "metadata": r.metadata,
                }
                for r in results
            ],
            total_count=len(results),
            search_time_ms=search_time_ms,
            cache_hit=False,
        )
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed")


# ============================================================================
# RAG QUERY ROUTES
# ============================================================================

@app.post("/api/v1/query", response_model=RAGQueryResponse)
async def rag_query(
    request: RAGQueryRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Execute RAG query."""
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    try:
        response = await rag_pipeline.query(
            request.query,
            str(current_user["tenant_id"]),
            request.top_k,
            request.temperature,
            request.max_tokens,
            request.filters,
            use_cache=settings.enable_semantic_cache,
        )
        
        return response
    except Exception as e:
        logger.error(f"RAG query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Query failed")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    services = {
        "database": "unknown",
        "redis": "unknown",
        "embedding": "unknown",
        "llm": "unknown",
    }
    
    status_value = "healthy"
    
    # Check services
    if embedding_service:
        services["embedding"] = "ready"
    else:
        services["embedding"] = "not_ready"
        status_value = "degraded"
    
    if llm_service:
        services["llm"] = "ready"
    else:
        services["llm"] = "not_ready"
        status_value = "degraded"
    
    if semantic_cache and semantic_cache._redis:
        services["redis"] = "connected"
    else:
        services["redis"] = "disconnected"
    
    return HealthCheckResponse(
        status=status_value,
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        services=services,
    )


@app.get("/ready")
async def readiness_check():
    """Readiness check for k8s."""
    if not embedding_service or not llm_service:
        raise HTTPException(status_code=503, detail="Not ready")
    
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
