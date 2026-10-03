"""
Database models for ATLAS platform.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid as UUID,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UserRole(str, enum.Enum):
    """User roles."""
    ADMIN = "admin"
    MEMBER = "member"


class DocumentStatus(str, enum.Enum):
    """Document processing status."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class JobStatus(str, enum.Enum):
    """Background job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Tenant(Base):
    """Multi-tenant workspace."""
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_tenants_slug", "slug"),
    )


class User(Base):
    """User account."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_email", "email"),
    )


class TenantMembership(Base):
    """User membership in a tenant."""
    __tablename__ = "tenant_memberships"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.MEMBER)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        Index("ix_memberships_tenant_id", "tenant_id"),
        Index("ix_memberships_user_id", "user_id"),
    )


class Collection(Base):
    """Document collection within a tenant."""
    __tablename__ = "collections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    attrs = Column(name='metadata', type_=JSON, nullable=True, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_collections_tenant_name"),
        Index("ix_collections_tenant_id", "tenant_id"),
    )


class Document(Base):
    """Uploaded document."""
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    content_checksum = Column(String(64), nullable=False)
    status = Column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.UPLOADED)
    storage_path = Column(String(500), nullable=False)
    error_message = Column(Text, nullable=True)
    attrs = Column(name='metadata', type_=JSON, nullable=True, default={})
    current_version_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_documents_tenant_id", "tenant_id"),
        Index("ix_documents_collection_id", "collection_id"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_checksum", "content_checksum"),
    )


class DocumentVersion(Base):
    """Document version history."""
    __tablename__ = "document_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    content_checksum = Column(String(64), nullable=False)
    storage_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_versions_doc_version"),
        Index("ix_versions_document_id", "document_id"),
        Index("ix_versions_tenant_id", "tenant_id"),
    )


class Chunk(Base):
    """Document chunks for RAG."""
    __tablename__ = "chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    section = Column(String(255), nullable=True)
    content_checksum = Column(String(64), nullable=False)
    attrs = Column(name='metadata', type_=JSON, nullable=True, default={})
    indexed = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="uq_chunks_version_index"),
        Index("ix_chunks_tenant_id", "tenant_id"),
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_document_version_id", "document_version_id"),
        Index("ix_chunks_indexed", "indexed"),
    )


class ProcessingJob(Base):
    """Background processing job."""
    __tablename__ = "processing_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    job_type = Column(String(50), nullable=False)  # parsing, chunking, embedding, etc.
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    progress = Column(Float, default=0.0)  # 0.0 to 1.0
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    attrs = Column(name='metadata', type_=JSON, nullable=True, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_jobs_tenant_id", "tenant_id"),
        Index("ix_jobs_document_id", "document_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_job_type", "job_type"),
    )


class EvaluationRun(Base):
    """RAG evaluation run."""
    __tablename__ = "evaluation_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dataset_path = Column(String(500), nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    total_examples = Column(Integer, default=0)
    completed_examples = Column(Integer, default=0)
    results = Column(JSON, nullable=True, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_evals_tenant_id", "tenant_id"),
        Index("ix_evals_status", "status"),
    )


class EvaluationResult(Base):
    """Individual evaluation result."""
    __tablename__ = "evaluation_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_run_id = Column(UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    actual_answer = Column(Text, nullable=True)
    retrieved_chunks = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True, default={})  # recall, precision, mrr, etc.
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_results_evaluation_run_id", "evaluation_run_id"),
        Index("ix_results_tenant_id", "tenant_id"),
    )


class AuditLog(Base):
    """Audit trail for sensitive operations."""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_audit_tenant_id", "tenant_id"),
        Index("ix_audit_user_id", "user_id"),
        Index("ix_audit_action", "action"),
    )
