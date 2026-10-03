"""
Pydantic schemas for API requests and responses.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Auth Schemas

class UserRegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None
    tenant_name: str = Field(..., min_length=1, max_length=255)


class UserLoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """User response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime


# Tenant Schemas

class TenantResponse(BaseModel):
    """Tenant response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime


# Collection Schemas

class CollectionCreateRequest(BaseModel):
    """Create collection request."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata: dict[str, Any] | None = None


class CollectionResponse(BaseModel):
    """Collection response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    description: str | None
    metadata: dict[str, Any] | None
    created_at: datetime


# Document Schemas

class DocumentMetadata(BaseModel):
    """Document metadata."""
    source_url: str | None = None
    tags: list[str] | None = None
    custom_fields: dict[str, Any] | None = None


class DocumentVersionResponse(BaseModel):
    """Document version response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    version_number: int
    content_checksum: str
    created_at: datetime


class DocumentResponse(BaseModel):
    """Document response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    filename: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    status: str
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    """Detailed document response with version info."""
    versions: list[DocumentVersionResponse] | None = None
    current_version_id: uuid.UUID | None = None


# Document Upload Response
class DocumentUploadResponse(BaseModel):
    """Response after document upload."""
    document_id: uuid.UUID
    filename: str
    status: str
    message: str


# Job Schemas

class JobStatusResponse(BaseModel):
    """Job status response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    job_type: str
    status: str
    progress: float
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProcessingJobResponse(JobStatusResponse):
    """Processing job response."""
    document_id: uuid.UUID
    retry_count: int


# Search & Retrieval Schemas

class ChunkResult(BaseModel):
    """Single retrieved chunk."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    document_version: int
    content: str
    page_number: int | None = None
    section: str | None = None
    score: float
    metadata: dict[str, Any] | None = None


class RetrievalResponse(BaseModel):
    """Retrieval results."""
    chunks: list[ChunkResult]
    total_count: int
    retrieval_time_ms: float


class SearchRequest(BaseModel):
    """Search request."""
    query: str = Field(..., min_length=1, max_length=1000)
    collection_ids: list[uuid.UUID] | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, Any] | None = None
    version: str | None = "latest"  # "latest", "all", or specific version


class SearchResponse(BaseModel):
    """Search response."""
    results: list[ChunkResult]
    total_count: int
    search_time_ms: float
    cache_hit: bool


# RAG Query Schemas

class Citation(BaseModel):
    """Citation metadata."""
    document_id: uuid.UUID
    document_name: str
    document_version: int
    chunk_id: uuid.UUID
    page_number: int | None = None
    section: str | None = None
    score: float


class RAGQueryRequest(BaseModel):
    """RAG query request."""
    query: str = Field(..., min_length=1, max_length=2000)
    collection_ids: list[uuid.UUID] | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    include_citations: bool = True
    filters: dict[str, Any] | None = None
    temperature: float | None = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=2000, ge=100, le=4000)


class RAGQueryResponse(BaseModel):
    """RAG query response."""
    request_id: str
    query: str
    answer: str
    citations: list[Citation]
    retrieval_time_ms: float
    generation_time_ms: float
    total_time_ms: float
    cache_hit: bool
    tokens_used: dict[str, int] | None = None
    error: str | None = None


# Evaluation Schemas

class EvaluationDataset(BaseModel):
    """Evaluation dataset entry."""
    question: str
    expected_answer: str | None = None
    expected_source_documents: list[uuid.UUID] | None = None


class EvaluationCreateRequest(BaseModel):
    """Create evaluation run."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    dataset: list[EvaluationDataset]


class EvaluationMetrics(BaseModel):
    """Evaluation metrics."""
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg: float
    citation_accuracy: float
    answer_relevance: float
    faithfulness: float | None = None
    average_latency_ms: float


class EvaluationRunResponse(BaseModel):
    """Evaluation run response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    status: str
    total_examples: int
    completed_examples: int
    results: dict[str, Any] | None
    created_at: datetime


# Error Response

class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_code: str | None = None
    request_id: str | None = None


# Health Check

class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    timestamp: datetime
    services: dict[str, str]  # service_name: status
