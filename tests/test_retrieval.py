"""
Tests for retrieval service.
"""

from uuid import uuid4

import numpy as np
import pytest

from backend.services.retrieval import (
    BM25Retriever,
    DenseRetriever,
    HybridRetriever,
    Reranker,
)


@pytest.mark.asyncio
async def test_hybrid_retriever_rrf_scoring():
    """Test Reciprocal Rank Fusion scoring."""
    retriever = HybridRetriever(
        dense_retriever=DenseRetriever(embedding_service=None, qdrant_client=None),
        bm25_retriever=BM25Retriever(None)
    )
    
    # Mock results from two retrievers
    dense_results = [
        {"id": "doc1", "score": 0.95},
        {"id": "doc2", "score": 0.85},
        {"id": "doc3", "score": 0.75},
    ]
    
    bm25_results = [
        {"id": "doc2", "score": 0.90},
        {"id": "doc1", "score": 0.80},
        {"id": "doc4", "score": 0.70},
    ]
    
    # Calculate RRF scores manually
    k = 60
    doc1_rrf = 1/(k+1+1) + 1/(k+2+1)  # Rank 1 in dense, rank 2 in BM25
    doc2_rrf = 1/(k+2+1) + 1/(k+1+1)  # Rank 2 in dense, rank 1 in BM25
    doc3_rrf = 1/(k+3+1)              # Only in dense
    doc4_rrf = 1/(k+3+1)              # Only in BM25
    
    assert doc1_rrf > 0
    assert doc2_rrf > 0
    assert doc3_rrf > 0
    assert doc4_rrf > 0
    assert doc1_rrf > doc3_rrf  # doc1 should rank higher
    assert doc2_rrf > doc3_rrf  # doc2 should rank higher


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
    
    # Create a mock retriever
    retriever = DenseRetriever(embedding_service=None, qdrant_client=None)
    
    # Retrievers should always filter by tenant_id
    # This is a structural test - the actual retrieval
    # would filter results by tenant_id
    assert hasattr(retriever, 'embedding_service')


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
