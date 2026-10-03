"""
Retrieval interfaces and implementations.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


@dataclass
class RetrievalScore:
    """Single retrieval result."""
    chunk_id: str
    document_id: str
    content: str
    score: float
    metadata: dict


class Retriever(ABC):
    """Abstract base retriever."""
    
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RetrievalScore]:
        """Retrieve chunks for a query."""


class DenseRetriever(Retriever):
    """Dense vector retrieval using Qdrant."""
    
    def __init__(self, embedding_service, qdrant_client):
        self.embedding_service = embedding_service
        self.qdrant = qdrant_client
    
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RetrievalScore]:
        """Retrieve using vector similarity."""
        try:
            # Embed query
            query_embedding = await self.embedding_service.embed(query)
            
            # Build filter for tenant isolation
            filter_conditions = {
                "must": [
                    {"key": "tenant_id", "match": {"value": str(tenant_id)}}
                ]
            }
            
            # Add custom filters if provided
            if filters:
                for key, value in filters.items():
                    filter_conditions["must"].append(
                        {"key": key, "match": {"value": value}}
                    )
            
            # Search in Qdrant
            results = await self.qdrant.search(
                collection_name="atlas-vectors",
                query_vector=query_embedding,
                query_filter=filter_conditions,
                limit=top_k,
            )
            
            scores = []
            for result in results:
                scores.append(
                    RetrievalScore(
                        chunk_id=result.payload.get("chunk_id"),
                        document_id=result.payload.get("document_id"),
                        content=result.payload.get("content"),
                        score=float(result.score),
                        metadata=result.payload.get("metadata", {}),
                    )
                )
            
            return scores
        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}")
            return []


class BM25Retriever(Retriever):
    """BM25 lexical retrieval."""
    
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
    
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RetrievalScore]:
        """Retrieve using BM25 ranking (SQL-based approximation)."""
        try:
            from backend.models import Chunk
            
            # Simple token matching for BM25 approximation
            # In production, use pg_trgm or dedicated BM25 library
            tokens = query.lower().split()
            
            if not tokens:
                return []
            
            query_obj = select(Chunk).where(
                Chunk.tenant_id == tenant_id
            )
            
            # Filter by tokens using SQLAlchemy parameterized queries (prevent SQL injection)
            for token in tokens:
                # Use concat operator to safely build LIKE pattern
                query_obj = query_obj.where(
                    Chunk.content.ilike("%" + token + "%")
                )
            
            query_obj = query_obj.limit(top_k)
            result = await self.session.execute(query_obj)
            chunks = result.scalars().all()
            
            scores = []
            for chunk in chunks:
                # Score based on token frequency
                score = sum(chunk.content.lower().count(token) for token in tokens) / len(tokens)
                
                scores.append(
                    RetrievalScore(
                        chunk_id=str(chunk.id),
                        document_id=str(chunk.document_id),
                        content=chunk.content,
                        score=float(score),
                        metadata=chunk.attrs or {},
                    )
                )
            
            # Sort by score
            scores.sort(key=lambda x: x.score, reverse=True)
            return scores[:top_k]
        except Exception as e:
            logger.error(f"BM25 retrieval failed: {e}")
            return []


class HybridRetriever(Retriever):
    """Hybrid retrieval combining dense and BM25 with RRF."""
    
    def __init__(self, dense_retriever: DenseRetriever, bm25_retriever: BM25Retriever):
        self.dense = dense_retriever
        self.bm25 = bm25_retriever
    
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RetrievalScore]:
        """Retrieve using Reciprocal Rank Fusion."""
        try:
            # Get results from both retrievers
            dense_results = await self.dense.retrieve(query, tenant_id, top_k, filters)
            bm25_results = await self.bm25.retrieve(query, tenant_id, top_k, filters)
            
            # RRF scoring
            rrf_scores = {}
            
            # Dense results
            for rank, result in enumerate(dense_results):
                score = 1.0 / (60 + rank + 1)  # RRF formula
                if result.chunk_id not in rrf_scores:
                    rrf_scores[result.chunk_id] = {"score": 0, "result": result}
                rrf_scores[result.chunk_id]["score"] += score
            
            # BM25 results
            for rank, result in enumerate(bm25_results):
                score = 1.0 / (60 + rank + 1)
                if result.chunk_id not in rrf_scores:
                    rrf_scores[result.chunk_id] = {"score": 0, "result": result}
                rrf_scores[result.chunk_id]["score"] += score
            
            # Sort by RRF score
            sorted_results = sorted(
                rrf_scores.values(),
                key=lambda x: x["score"],
                reverse=True
            )
            
            # Return top-k with combined score
            results = []
            for item in sorted_results[:top_k]:
                result = item["result"]
                result.score = item["score"]
                results.append(result)
            
            return results
        except Exception as e:
            logger.error(f"Hybrid retrieval failed: {e}")
            return []


class Reranker:
    """Cross-encoder based reranking."""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"):
        self.model_name = model_name
        self._model = None
    
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalScore],
        top_k: int = 5,
    ) -> list[RetrievalScore]:
        """Rerank candidates using cross-encoder."""
        try:
            if not candidates:
                return []
            
            # Lazy load model
            if self._model is None:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
            
            # Prepare pairs for reranking
            pairs = [
                [query, candidate.content]
                for candidate in candidates
            ]
            
            # Score
            scores = self._model.predict(pairs, show_progress_bar=False)
            
            # Update scores
            for candidate, score in zip(candidates, scores):
                candidate.score = float(score)
            
            # Sort and return top-k
            candidates.sort(key=lambda x: x.score, reverse=True)
            return candidates[:top_k]
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return candidates[:top_k]
