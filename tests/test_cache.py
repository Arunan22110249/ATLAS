"""
Tests for caching service.
"""

from uuid import uuid4

import pytest

from backend.services.cache import SemanticCache


@pytest.mark.asyncio
async def test_cache_set_get(redis_client):
    """Test cache set and get."""
    cache = SemanticCache(redis_client)
    
    tenant_id = uuid4()
    query = "What is machine learning?"
    response = {
        "answer": "ML is a subset of AI",
        "citations": []
    }
    
    # Set cache
    await cache.set(tenant_id, query, response)
    
    # Get from cache
    cached = await cache.get(tenant_id, query)
    
    assert cached is not None
    assert cached["answer"] == response["answer"]


@pytest.mark.asyncio
async def test_cache_hit_miss(redis_client):
    """Test cache hit vs miss."""
    cache = SemanticCache(redis_client)
    
    tenant_id = uuid4()
    query1 = "Question 1"
    query2 = "Question 2"
    
    response = {"answer": "Answer"}
    
    # Set cache for query1
    await cache.set(tenant_id, query1, response)
    
    # Query1 should hit
    hit1 = await cache.get(tenant_id, query1)
    assert hit1 is not None
    
    # Query2 should miss
    hit2 = await cache.get(tenant_id, query2)
    assert hit2 is None


@pytest.mark.asyncio
async def test_cache_invalidation_by_document(redis_client):
    """Test cache invalidation when document changes."""
    cache = SemanticCache(redis_client)
    
    tenant_id = uuid4()
    doc_id = uuid4()
    
    # Set some cached responses
    query = "What is in the document?"
    response = {"answer": "Document content", "document_ids": [str(doc_id)]}
    
    await cache.set(tenant_id, query, response)
    
    # Invalidate by document
    await cache.invalidate_by_document(tenant_id, doc_id)
    
    # Cache should now be cleared
    cached = await cache.get(tenant_id, query)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_ttl_expiration(redis_client):
    """Test that cached items expire after TTL."""
    cache = SemanticCache(redis_client)
    
    tenant_id = uuid4()
    query = "Temporary query"
    response = {"answer": "Temporary answer"}
    
    # Set with short TTL
    await cache.set(tenant_id, query, response, ttl_seconds=1)
    
    # Should exist immediately
    cached = await cache.get(tenant_id, query)
    assert cached is not None
    
    # Wait for TTL to expire
    import asyncio
    await asyncio.sleep(2)
    
    # Should be expired
    expired = await cache.get(tenant_id, query)
    assert expired is None


@pytest.mark.asyncio
async def test_cache_tenant_isolation(redis_client):
    """Test that cache is tenant-isolated."""
    cache = SemanticCache(redis_client)
    
    tenant_a = uuid4()
    tenant_b = uuid4()
    
    query = "Same question"
    response_a = {"answer": "Answer from tenant A"}
    response_b = {"answer": "Answer from tenant B"}
    
    # Set in both tenants
    await cache.set(tenant_a, query, response_a)
    await cache.set(tenant_b, query, response_b)
    
    # Retrieve from each tenant
    cached_a = await cache.get(tenant_a, query)
    cached_b = await cache.get(tenant_b, query)
    
    # Should get tenant-specific responses
    assert cached_a["answer"] == "Answer from tenant A"
    assert cached_b["answer"] == "Answer from tenant B"


@pytest.mark.asyncio
async def test_cache_clear(redis_client):
    """Test cache clearing."""
    cache = SemanticCache(redis_client)
    
    tenant_id = uuid4()
    
    # Set multiple items
    for i in range(5):
        query = f"Query {i}"
        response = {"answer": f"Answer {i}"}
        await cache.set(tenant_id, query, response)
    
    # Clear all
    await cache.clear(tenant_id)
    
    # All should be gone
    for i in range(5):
        query = f"Query {i}"
        cached = await cache.get(tenant_id, query)
        assert cached is None


@pytest.mark.asyncio
async def test_cache_stats(redis_client):
    """Test cache statistics."""
    cache = SemanticCache(redis_client)
    
    tenant_id = uuid4()
    
    # Set cache
    await cache.set(tenant_id, "Query 1", {"answer": "Answer 1"})
    await cache.set(tenant_id, "Query 2", {"answer": "Answer 2"})
    
    # Get stats
    stats = await cache.get_stats()
    
    assert stats is not None
    assert isinstance(stats, dict)
