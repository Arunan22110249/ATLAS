"""
RAG pipeline for end-to-end query processing.
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas import Citation, RAGQueryResponse
from backend.services.cache import SemanticCache
from backend.services.embedding import EmbeddingService
from backend.services.llm import LLMService
from backend.services.retrieval import Reranker, Retriever

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on provided documents.
- Answer questions directly and concisely
- If you cannot answer based on the provided context, say "I don't have enough information to answer this question"
- Never fabricate citations or make up information
- Cite your sources by including document names and page numbers when available
- Format: [Document Name, Page X] or [Document Name]"""

RAG_PROMPT_TEMPLATE = """Based on the following documents, answer the question.

DOCUMENTS:
{context}

QUESTION: {question}

ANSWER:"""


class RAGPipeline:
    """End-to-end RAG query pipeline."""
    
    def __init__(
        self,
        retriever: Retriever,
        reranker: Reranker | None,
        embedding_service: EmbeddingService,
        llm_service: LLMService,
        cache: SemanticCache | None = None,
        session: AsyncSession | None = None,
    ):
        self.retriever = retriever
        self.reranker = reranker
        self.embedding = embedding_service
        self.llm = llm_service
        self.cache = cache
        self.session = session
    
    async def query(
        self,
        query_text: str,
        tenant_id: str,
        top_k: int = 10,
        temperature: float | None = None,
        max_tokens: int | None = None,
        filters: dict | None = None,
        use_cache: bool = True,
    ) -> RAGQueryResponse:
        """Execute RAG query."""
        import uuid
        request_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        try:
            # Check cache
            cache_hit = False
            if self.cache and use_cache:
                cached_response = await self.cache.get(query_text, tenant_id)
                if cached_response:
                    cache_hit = True
                    logger.info(f"Cache hit for query: {query_text[:50]}")
                    return cached_response
            
            # Retrieval
            retrieval_start = datetime.utcnow()
            candidates = await self.retriever.retrieve(
                query_text,
                tenant_id,
                top_k,
                filters,
            )
            retrieval_time = (datetime.utcnow() - retrieval_start).total_seconds() * 1000
            
            # Check if we have sufficient evidence
            if not candidates or all(c.score < 0.3 for c in candidates):
                logger.warning(f"Insufficient retrieval evidence for query: {query_text[:50]}")
                return RAGQueryResponse(
                    request_id=request_id,
                    query=query_text,
                    answer="I don't have enough information to answer this question based on the available documents.",
                    citations=[],
                    retrieval_time_ms=retrieval_time,
                    generation_time_ms=0,
                    total_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
                    cache_hit=cache_hit,
                    error=None,
                )
            
            # Rerank if available
            if self.reranker:
                rerank_start = datetime.utcnow()
                candidates = await self.reranker.rerank(query_text, candidates, top_k=5)
                rerank_time = (datetime.utcnow() - rerank_start).total_seconds() * 1000
                logger.info(f"Reranking took {rerank_time:.1f}ms")
            
            # Build context
            context_parts = []
            citations = []
            
            for candidate in candidates:
                context_parts.append(
                    f"[{candidate.metadata.get('source_filename', 'Unknown')} - "
                    f"p.{candidate.metadata.get('page_number', '?')}]\n"
                    f"{candidate.content}"
                )
                
                citations.append(
                    Citation(
                        document_id=candidate.document_id,
                        document_name=candidate.metadata.get("source_filename", "Unknown"),
                        document_version=candidate.metadata.get("document_version", 1),
                        chunk_id=candidate.chunk_id,
                        page_number=candidate.metadata.get("page_number"),
                        section=candidate.metadata.get("section"),
                        score=candidate.score,
                    )
                )
            
            context = "\n\n".join(context_parts)
            
            # Generate answer
            generation_start = datetime.utcnow()
            prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=query_text)
            
            llm_response = await self.llm.generate(
                prompt=prompt,
                system_prompt=RAG_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            if not llm_response:
                return RAGQueryResponse(
                    request_id=request_id,
                    query=query_text,
                    answer="Failed to generate response. Please try again.",
                    citations=[],
                    retrieval_time_ms=retrieval_time,
                    generation_time_ms=0,
                    total_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
                    cache_hit=cache_hit,
                    error="LLM generation failed",
                )
            
            generation_time = (datetime.utcnow() - generation_start).total_seconds() * 1000
            total_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Build response
            response = RAGQueryResponse(
                request_id=request_id,
                query=query_text,
                answer=llm_response.text,
                citations=citations,
                retrieval_time_ms=retrieval_time,
                generation_time_ms=generation_time,
                total_time_ms=total_time,
                cache_hit=cache_hit,
                tokens_used={
                    "input": llm_response.tokens_input,
                    "output": llm_response.tokens_output,
                },
            )
            
            # Cache response
            if self.cache and use_cache:
                await self.cache.set(query_text, tenant_id, response)
            
            return response
        
        except Exception as e:
            logger.error(f"RAG pipeline error: {e}", exc_info=True)
            return RAGQueryResponse(
                request_id=request_id,
                query=query_text,
                answer="An error occurred while processing your query.",
                citations=[],
                retrieval_time_ms=0,
                generation_time_ms=0,
                total_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
                cache_hit=False,
                error=str(e),
            )
