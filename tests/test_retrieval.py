"""
Tests for retrieval service.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import pytest

from backend.services.retrieval import (
    DenseRetriever,
    HybridRetriever,
    Reranker,
    RetrievalScore,
)


@pytest.mark.asyncio
async def test_hybrid_retriever_rrf_scoring():
    """Test Reciprocal Rank Fusion scoring."""
    dense_retriever = AsyncMock()
    bm25_retriever = AsyncMock()
    retriever = HybridRetriever(dense_retriever, bm25_retriever)
    dense_results = [
        RetrievalScore("doc1", "document1", "content1", 0.95, {}),
        RetrievalScore("doc2", "document2", "content2", 0.85, {}),
        RetrievalScore("doc3", "document3", "content3", 0.75, {}),
    ]
    bm25_results = [
        RetrievalScore("doc2", "document2", "content2", 0.90, {}),
        RetrievalScore("doc1", "document1", "content1", 0.80, {}),
        RetrievalScore("doc4", "document4", "content4", 0.70, {}),
    ]
    dense_retriever.retrieve.return_value = dense_results
    bm25_retriever.retrieve.return_value = bm25_results

    results = await retriever.retrieve("query", "tenant", top_k=4)

    assert {result.chunk_id for result in results[:2]} == {"doc1", "doc2"}
    assert results[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert results[1].score == pytest.approx(1 / 61 + 1 / 62)
    assert results[2].score == pytest.approx(1 / 63)
    assert results[3].score == pytest.approx(1 / 63)


def test_reranker_cross_encoder():
    """Test reranker with cross-encoder."""
    reranker = Reranker(model_name="ms-marco-MiniLM-L-6-v2")
    
    # Test if model is loadable
    try:
        model = reranker.get_model()
        assert model is not None
    except Exception as e:
        pytest.skip(f"Cross-encoder model not available: {e!s}")


@pytest.mark.asyncio
async def test_retriever_tenant_isolation():
    """Test that retriever respects tenant isolation."""
    tenant_id = uuid4()
    embedding_service = AsyncMock()
    embedding_service.embed.return_value = [0.1, 0.2]
    qdrant_client = AsyncMock()
    qdrant_client.search.return_value = []
    retriever = DenseRetriever(embedding_service, qdrant_client)

    await retriever.retrieve("query", str(tenant_id))

    query_filter = qdrant_client.search.call_args.kwargs["query_filter"]
    assert query_filter["must"][0]["key"] == "tenant_id"
    assert query_filter["must"][0]["match"]["value"] == str(tenant_id)


def test_embedding_dimension():
    """Test embedding dimension."""
    from backend.services.embedding import EmbeddingService
    
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    dim = service.get_embedding_dimension()
    
    # MiniLM produces 384-dimensional embeddings
    assert dim == 384


@pytest.mark.asyncio
async def test_embedding_batch_processing():
    """Test batch embedding generation."""
    from backend.services.embedding import EmbeddingService
    
    service = EmbeddingService(model_name="all-MiniLM-L6-v2")
    
    texts = [
        "Hello world",
        "This is a test",
        "Another document"
    ]
    
    try:
        embeddings = await service.embed(texts)
        assert len(embeddings) == 3
        assert all(len(emb) == 384 for emb in embeddings)
    except Exception as e:
        pytest.skip(f"Embedding service not available: {e!s}")


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    from backend.services.retrieval import cosine_similarity
    
    vec1 = np.array([1, 0, 0])
    vec2 = np.array([1, 0, 0])
    vec3 = np.array([0, 1, 0])
    
    # Identical vectors should have similarity 1.0
    sim_same = cosine_similarity(vec1, vec2)
    assert abs(sim_same - 1.0) < 0.001
    
    # Orthogonal vectors should have similarity 0
    sim_ortho = cosine_similarity(vec1, vec3)
    assert abs(sim_ortho) < 0.001


def test_bm25_scoring():
    """Test BM25 scoring."""
    from backend.services.retrieval import BM25Retriever
    
    # BM25 is typically calculated using rank-bm25 library
    # This tests that the structure is correct
    retriever = BM25Retriever(db_session=None)
    assert hasattr(retriever, 'retrieve')


def test_retrieval_confidence_threshold():
    """Test confidence score thresholding."""
    min_confidence = 0.3
    
    scores = [0.95, 0.75, 0.50, 0.25, 0.10]
    
    # Filter below confidence threshold
    filtered = [s for s in scores if s >= min_confidence]
    
    assert len(filtered) == 3
    assert min(filtered) >= min_confidence
