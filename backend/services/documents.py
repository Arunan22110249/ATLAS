"""
Document management service.
"""

import hashlib
import logging
import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    JobStatus,
    ProcessingJob,
)

logger = logging.getLogger(__name__)


def calculate_checksum(content: bytes) -> str:
    """Calculate SHA256 checksum of file content."""
    return hashlib.sha256(content).hexdigest()


async def _create_document(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    filename: str,
    original_filename: str,
    mime_type: str,
    file_size_bytes: int,
    content_checksum: str,
    storage_path: str,
    collection_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> Document:
    """Create a new document record."""
    doc = Document(
        tenant_id=tenant_id,
        collection_id=collection_id,
        filename=filename,
        original_filename=original_filename,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        content_checksum=content_checksum,
        storage_path=storage_path,
        status=DocumentStatus.UPLOADED,
        attrs=metadata or {},
    )
    session.add(doc)
    await session.flush()
    
    # Create initial version
    version = DocumentVersion(
        document_id=doc.id,
        tenant_id=tenant_id,
        version_number=1,
        content_checksum=content_checksum,
        storage_path=storage_path,
    )
    session.add(version)
    await session.flush()
    
    doc.current_version_id = version.id
    session.add(doc)
    
    return doc


async def _get_document_by_id(
    session: AsyncSession,
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Document | None:
    """Get document by ID with tenant isolation."""
    result = await session.execute(
        select(Document).where(
            and_(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
                Document.status != DocumentStatus.DELETED,
            )
        )
    )
    return result.scalars().first()


async def _get_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID | None = None,
    status: DocumentStatus | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Document], int]:
    """Get documents with optional filtering."""
    query = select(Document).where(Document.tenant_id == tenant_id)
    
    if collection_id:
        query = query.where(Document.collection_id == collection_id)
    
    if status:
        query = query.where(Document.status == status)
    
    # Get total count
    count_result = await session.execute(
        select(Document).where(Document.tenant_id == tenant_id)
    )
    total = len(count_result.scalars().all())
    
    # Get paginated results
    query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    documents = result.scalars().all()
    
    return documents, total


async def _check_duplicate_document(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    content_checksum: str,
) -> Document | None:
    """Check if document with same content already exists."""
    result = await session.execute(
        select(Document).where(
            and_(
                Document.tenant_id == tenant_id,
                Document.content_checksum == content_checksum,
                Document.status != DocumentStatus.DELETED,
            )
        )
    )
    return result.scalars().first()


async def _update_document_status(
    session: AsyncSession,
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
    status: DocumentStatus,
    error_message: str | None = None,
) -> Document | None:
    """Update document processing status."""
    doc = await _get_document_by_id(session, document_id, tenant_id)
    if not doc:
        return None
    
    doc.status = status
    if error_message:
        doc.error_message = error_message
    doc.updated_at = datetime.utcnow()
    
    session.add(doc)
    return doc


async def _create_processing_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    job_type: str,
    max_retries: int = 3,
    metadata: dict | None = None,
) -> ProcessingJob:
    """Create a processing job."""
    job = ProcessingJob(
        tenant_id=tenant_id,
        document_id=document_id,
        job_type=job_type,
        status=JobStatus.PENDING,
        max_retries=max_retries,
        attrs=metadata or {},
    )
    session.add(job)
    await session.flush()
    return job


async def _get_processing_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> ProcessingJob | None:
    """Get processing job by ID."""
    result = await session.execute(
        select(ProcessingJob).where(
            and_(
                ProcessingJob.id == job_id,
                ProcessingJob.tenant_id == tenant_id,
            )
        )
    )
    return result.scalars().first()


async def _update_job_status(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: JobStatus,
    progress: float = 0.0,
    error_message: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ProcessingJob | None:
    """Update processing job status."""
    result = await session.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_id)
    )
    job = result.scalars().first()
    
    if not job:
        return None
    
    job.status = status
    job.progress = min(1.0, max(0.0, progress))
    
    if error_message:
        job.error_message = error_message
    
    if started_at:
        job.started_at = started_at
    
    if completed_at:
        job.completed_at = completed_at
    
    session.add(job)
    return job


async def _increment_job_retry_count(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> ProcessingJob | None:
    """Increment retry count for a job."""
    result = await session.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_id)
    )
    job = result.scalars().first()
    
    if not job:
        return None
    
    job.retry_count += 1
    session.add(job)
    return job


async def _get_pending_jobs(
    session: AsyncSession,
    job_type: str | None = None,
    limit: int = 100,
) -> list[ProcessingJob]:
    """Get pending or running jobs."""
    query = select(ProcessingJob).where(
        ProcessingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
    )
    
    if job_type:
        query = query.where(ProcessingJob.job_type == job_type)
    
    query = query.limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def _delete_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Document | None:
    """Soft delete a document."""
    doc = await _get_document_by_id(session, document_id, tenant_id)
    if not doc:
        return None
    
    doc.status = DocumentStatus.DELETED
    doc.updated_at = datetime.utcnow()
    session.add(doc)
    return doc


async def _get_document_versions(
    session: AsyncSession,
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> list[DocumentVersion]:
    """Get all versions of a document."""
    result = await session.execute(
        select(DocumentVersion).where(
            and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.tenant_id == tenant_id,
            )
        ).order_by(DocumentVersion.version_number.desc())
    )
    return result.scalars().all()


# Service class for tests and main API compatibility
class DocumentService:
    """Document service with static methods wrapping module functions."""
    
    @staticmethod
    async def create_document(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        filename: str,
        original_filename: str,
        mime_type: str,
        file_size_bytes: int,
        content_checksum: str,
        storage_path: str,
        collection_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> Document:
        """Create a new document record."""
        return await _create_document(
            session, tenant_id, filename, original_filename, mime_type,
            file_size_bytes, content_checksum, storage_path, collection_id, metadata
        )
    
    @staticmethod
    async def get_document_by_id(
        session: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Document | None:
        """Get document by ID with tenant isolation."""
        return await _get_document_by_id(session, document_id, tenant_id)
    
    @staticmethod
    async def get_documents(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        """Get documents with optional filtering."""
        return await _get_documents(session, tenant_id, collection_id, status, skip, limit)
    
    @staticmethod
    async def check_duplicate_document(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        content_checksum: str,
    ) -> Document | None:
        """Check if document with same content already exists."""
        return await _check_duplicate_document(session, tenant_id, content_checksum)
    
    @staticmethod
    async def update_document_status(
        session: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        status: DocumentStatus,
        error_message: str | None = None,
    ) -> Document | None:
        """Update document processing status."""
        return await _update_document_status(session, document_id, tenant_id, status, error_message)
    
    @staticmethod
    async def create_processing_job(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        job_type: str,
        max_retries: int = 3,
        metadata: dict | None = None,
    ) -> ProcessingJob:
        """Create a processing job."""
        return await _create_processing_job(session, tenant_id, document_id, job_type, max_retries, metadata)
    
    @staticmethod
    async def get_processing_job(
        session: AsyncSession,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> ProcessingJob | None:
        """Get processing job by ID."""
        return await _get_processing_job(session, job_id, tenant_id)
    
    @staticmethod
    async def update_job_status(
        session: AsyncSession,
        job_id: uuid.UUID,
        status: JobStatus,
        progress: float = 0.0,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> ProcessingJob | None:
        """Update processing job status."""
        return await _update_job_status(session, job_id, status, progress, error_message, started_at, completed_at)
    
    @staticmethod
    async def increment_job_retry_count(
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> ProcessingJob | None:
        """Increment retry count for a job."""
        return await _increment_job_retry_count(session, job_id)
    
    @staticmethod
    async def get_pending_jobs(
        session: AsyncSession,
        job_type: str | None = None,
        limit: int = 100,
    ) -> list[ProcessingJob]:
        """Get pending or running jobs."""
        return await _get_pending_jobs(session, job_type, limit)
    
    @staticmethod
    async def delete_document(
        session: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Document | None:
        """Soft delete a document."""
        return await _delete_document(session, document_id, tenant_id)
    
    @staticmethod
    async def _get_document_versions(
        session: AsyncSession,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> list[DocumentVersion]:
        """Get all versions of a document."""
        return await _get_document_versions(session, document_id, tenant_id)

