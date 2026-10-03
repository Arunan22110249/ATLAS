"""
Tests for document service.
"""

from uuid import uuid4

import pytest

from backend.models import DocumentStatus
from backend.services.documents import DocumentService


@pytest.mark.asyncio
async def test_create_document(async_session):
    """Test document creation."""
    tenant_id = uuid4()
    
    doc = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_id,
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="abc123",
        storage_path="/storage/test.pdf"
    )
    
    assert doc.tenant_id == tenant_id
    assert doc.filename == "test.pdf"
    assert doc.status == DocumentStatus.UPLOADED


@pytest.mark.asyncio
async def test_get_document(async_session):
    """Test document retrieval."""
    tenant_id = uuid4()
    
    # Create document
    doc = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_id,
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="abc123",
        storage_path="/storage/test.pdf"
    )
    await async_session.commit()
    
    # Retrieve document
    retrieved = await DocumentService.get_document_by_id(
        async_session,
        doc.id,
        tenant_id
    )
    
    assert retrieved is not None
    assert retrieved.id == doc.id
    assert retrieved.filename == "test.pdf"


@pytest.mark.asyncio
async def test_document_deduplication(async_session):
    """Test duplicate detection."""
    tenant_id = uuid4()
    checksum = "abc123"
    
    # Create first document
    doc1 = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_id,
        filename="test1.pdf",
        original_filename="test1.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum=checksum,
        storage_path="/storage/test1.pdf"
    )
    await async_session.commit()
    
    # Check for duplicate
    is_dup = await DocumentService.check_duplicate_document(
        async_session,
        tenant_id,
        checksum
    )
    
    assert is_dup is not None


@pytest.mark.asyncio
async def test_document_status_update(async_session):
    """Test document status update."""
    tenant_id = uuid4()
    
    doc = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_id,
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="abc123",
        storage_path="/storage/test.pdf"
    )
    await async_session.commit()
    
    # Update status
    updated = await DocumentService.update_document_status(
        async_session,
        doc.id,
        tenant_id,
        DocumentStatus.PROCESSING
    )
    
    assert updated.status == DocumentStatus.PROCESSING


@pytest.mark.asyncio
async def test_processing_job_creation(async_session):
    """Test processing job creation."""
    tenant_id = uuid4()
    
    doc = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_id,
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="abc123",
        storage_path="/storage/test.pdf"
    )
    await async_session.commit()
    
    job = await DocumentService.create_processing_job(
        async_session,
        tenant_id=tenant_id,
        document_id=doc.id,
        job_type="ingestion"
    )
    
    assert job.document_id == doc.id
    assert job.job_type == "ingestion"


@pytest.mark.asyncio
async def test_multi_tenant_isolation(async_session):
    """Test that documents from different tenants are isolated."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    
    # Create documents in different tenants
    doc_a = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_a,
        filename="test_a.pdf",
        original_filename="test_a.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="abc123",
        storage_path="/storage/test_a.pdf"
    )
    await async_session.commit()
    
    doc_b = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_b,
        filename="test_b.pdf",
        original_filename="test_b.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="def456",
        storage_path="/storage/test_b.pdf"
    )
    await async_session.commit()
    
    # Tenant A should not see document B
    doc_not_found = await DocumentService.get_document_by_id(
        async_session,
        doc_b.id,
        tenant_a
    )
    
    assert doc_not_found is None


@pytest.mark.asyncio
async def test_document_delete(async_session):
    """Test document soft delete."""
    tenant_id = uuid4()
    
    doc = await DocumentService.create_document(
        async_session,
        tenant_id=tenant_id,
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        content_checksum="abc123",
        storage_path="/storage/test.pdf"
    )
    await async_session.commit()
    
    # Delete document
    deleted = await DocumentService.delete_document(
        async_session,
        doc.id,
        tenant_id
    )
    
    assert deleted is not None
    assert deleted.status == DocumentStatus.DELETED
    
    # Deleted document should not be retrievable
    not_found = await DocumentService.get_document_by_id(
        async_session,
        doc.id,
        tenant_id
    )
    
    assert not_found is None
