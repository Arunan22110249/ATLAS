"""
Ingestion pipeline worker for processing documents.

This worker consumes events from Kafka and processes documents:
1. Parse document (PDF, DOCX, TXT, etc.)
2. Clean and normalize content
3. Chunk into smaller pieces
4. Enrich metadata
5. Generate embeddings
6. Index in Qdrant
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime

from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class DocumentIngestionWorker:
    """Main ingestion worker."""
    
    def __init__(
        self,
        kafka_brokers: str = "localhost:9092",
        db_url: str = "postgresql+asyncpg://atlas:atlas@localhost:5432/atlas",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.kafka_brokers = kafka_brokers.split(",")
        self.db_url = db_url
        self.embedding_model = embedding_model
        
        # Database
        self.engine = None
        self.async_session_maker = None
        
        # Kafka
        self.consumer = None
        self.producer = None
        
        # Services
        self.embedding_service = None
    
    async def initialize(self):
        """Initialize worker."""
        logger.info("Initializing ingestion worker")
        
        # Database
        self.engine = create_async_engine(self.db_url)
        self.async_session_maker = async_sessionmaker(self.engine)
        
        # Kafka consumer
        self.consumer = KafkaConsumer(
            "document-ingestion",
            bootstrap_servers=self.kafka_brokers,
            group_id="atlas-ingestion-workers",
            auto_offset_reset="earliest",
            enable_auto_commit=False,  # CRITICAL: Disable auto-commit to prevent message loss
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        
        # Kafka producer for DLQ
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        
        # Embedding service
        from backend.services.embedding import EmbeddingService
        self.embedding_service = EmbeddingService(self.embedding_model)
        
        logger.info("Ingestion worker initialized")
    
    async def shutdown(self):
        """Shutdown worker."""
        logger.info("Shutting down ingestion worker")
        
        if self.consumer:
            self.consumer.close()
        
        if self.producer:
            self.producer.close()
        
        if self.engine:
            await self.engine.dispose()
        
        logger.info("Worker shutdown complete")
    
    async def process_message(self, message: dict) -> bool:
        """Process a single ingestion message. Returns True if successful."""
        job_id = message.get("job_id")
        document_id = message.get("document_id")
        tenant_id = message.get("tenant_id")
        
        logger.info(f"Processing job {job_id} for document {document_id}")
        
        try:
            async with self.async_session_maker() as session:
                # Get document
                from sqlalchemy import select

                from backend.models import Document, JobStatus, ProcessingJob
                
                result = await session.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                document = result.scalars().first()
                
                if not document:
                    logger.error(f"Document not found: {document_id}")
                    return False
                
                # Get job
                result = await session.execute(
                    select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id))
                )
                job = result.scalars().first()
                
                if not job:
                    logger.error(f"Job not found: {job_id}")
                    return False
                
                # Idempotency check: if already completed, return success (duplicate message)
                if job.status == JobStatus.COMPLETED:
                    logger.info(f"Job {job_id} already completed, skipping (idempotent replay)")
                    return True
                
                # Prevent reprocessing if already in progress (unless retry)
                if job.status == JobStatus.RUNNING and job.retry_count == 0:
                    logger.warning(f"Job {job_id} already running, skipping duplicate")
                    return False
                
                # Update job status
                job.status = JobStatus.RUNNING
                job.started_at = datetime.utcnow()
                session.add(job)
                await session.commit()
                
                # Process document
                try:
                    # 1. Parse document
                    logger.info(f"Parsing document: {document.original_filename}")
                    content = await self._parse_document(document)
                    
                    # 2. Clean content
                    logger.info("Cleaning content")
                    cleaned_content = self._clean_content(content)
                    
                    # 3. Chunk content
                    logger.info("Chunking content")
                    chunks = self._chunk_content(
                        cleaned_content,
                        chunk_size=512,
                        chunk_overlap=50,
                    )
                    
                    # 4. Generate embeddings and store chunks
                    logger.info(f"Embedding {len(chunks)} chunks")
                    await self._embed_and_store_chunks(
                        session,
                        document,
                        chunks,
                    )
                    
                    # Update document status
                    document.status = "ready"
                    session.add(document)
                    
                    # Complete job
                    job.status = JobStatus.COMPLETED
                    job.progress = 1.0
                    job.completed_at = datetime.utcnow()
                    session.add(job)
                    
                    await session.commit()
                    logger.info(f"Successfully processed document: {document_id}")
                    return True
                
                except Exception as e:
                    logger.error(f"Processing error: {e}", exc_info=True)
                    
                    # Update job with error
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()
                    session.add(job)
                    
                    # Update document status
                    document.status = "failed"
                    document.error_message = str(e)
                    session.add(document)
                    
                    await session.commit()
                    
                    # Send to DLQ if max retries exceeded
                    if job.retry_count >= job.max_retries:
                        logger.error(f"Max retries exceeded for job {job_id}")
                        self._send_to_dlq(message)
                    
                    return False
        
        except Exception as e:
            logger.error(f"Unexpected error in message processing: {e}", exc_info=True)
            self._send_to_dlq(message)
            return False
    
    async def _parse_document(self, document) -> str:
        """Parse document content based on mime type."""
        # This would implement parsers for different document types
        # For now, placeholder
        logger.warning(f"Document parsing not yet implemented for {document.mime_type}")
        return ""
    
    def _clean_content(self, content: str) -> str:
        """Clean and normalize content."""
        import re
        
        # Remove extra whitespace
        content = re.sub(r"\s+", " ", content)
        
        # Remove special characters
        content = re.sub(r"[^\w\s\.\,\!\?\-\(\)\:]", "", content)
        
        return content.strip()
    
    def _chunk_content(
        self,
        content: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> list[str]:
        """Split content into overlapping chunks."""
        chunks = []
        start = 0
        
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunk = content[start:end]
            chunks.append(chunk)
            
            start += chunk_size - chunk_overlap
        
        return chunks
    
    async def _embed_and_store_chunks(self, session: AsyncSession, document, chunks: list[str]):
        """Generate embeddings and store chunks in database and Qdrant."""
        from sqlalchemy import select

        from backend.models import Chunk, DocumentVersion
        
        # Get current version (or create if doesn't exist)
        result = await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id
            ).order_by(DocumentVersion.version_number.desc())
        )
        version = result.scalars().first()
        
        # If no version exists, create one (should not happen in normal flow, but defensive)
        if not version:
            logger.warning(f"No DocumentVersion found for document {document.id}, creating initial version")
            version = DocumentVersion(
                document_id=document.id,
                tenant_id=document.tenant_id,
                version_number=1,
                content_checksum=document.content_checksum,
                storage_path=document.storage_path,
            )
            session.add(version)
            await session.flush()
        
        # Embed chunks in batch
        embeddings = await self.embedding_service.embed_async_batch(chunks, batch_size=32)
        
        # Store chunks in database
        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk = Chunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                document_version_id=version.id,
                content=chunk_text,
                chunk_index=i,
                attrs={
                    "source_filename": document.original_filename,
                    "document_version": version.version_number,
                },
                indexed=False,
            )
            session.add(chunk)
        
        await session.commit()
        logger.info(f"Stored {len(chunks)} chunks")
        
        # Store embeddings in Qdrant
        await self._store_embeddings_in_qdrant(session, document, embeddings)
    
    async def _store_embeddings_in_qdrant(self, session: AsyncSession, document, embeddings):
        """Store embeddings in Qdrant."""
        # TODO: Implement Qdrant integration
        logger.warning("Qdrant storage not yet implemented")
    
    def _send_to_dlq(self, message: dict):
        """Send message to dead-letter queue."""
        try:
            self.producer.send(
                "document-ingestion-dlq",
                value={**message, "timestamp": datetime.utcnow().isoformat()},
            )
            logger.info(f"Sent message to DLQ: {message.get('job_id')}")
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
    
    async def run(self):
        """Main worker loop."""
        await self.initialize()
        
        try:
            logger.info("Ingestion worker running")
            
            for message in self.consumer:
                # Process message and only commit offset if successful
                success = await self.process_message(message.value)
                
                if success:
                    # Manually commit offset only after successful processing
                    self.consumer.commit()
                    logger.debug(f"Offset committed for message: {message.offset}")
        
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        
        finally:
            await self.shutdown()


async def main():
    """Main entry point."""
    worker = DocumentIngestionWorker()
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
