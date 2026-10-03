"""
Embedding service for document chunks and queries.
"""

import asyncio
import logging

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Provider-agnostic embedding service."""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._model_lock = asyncio.Lock()
    
    async def _get_model(self):
        """Lazy load embedding model."""
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                        self._model = SentenceTransformer(self.model_name)
                    except Exception as e:
                        logger.error(f"Failed to load embedding model: {e}")
                        raise
        return self._model
    
    async def embed(self, text: str | list[str], batch_size: int = 32) -> np.ndarray:
        """
        Embed text or batch of texts.
        
        Returns:
            Embedding vector(s) as numpy array.
        """
        try:
            model = await self._get_model()
            
            if isinstance(text, str):
                # Single text
                embedding = model.encode(text, convert_to_numpy=True)
                return embedding
            else:
                # Batch
                embeddings = model.encode(
                    text,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                return embeddings
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise
    
    async def embed_async_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[np.ndarray]:
        """
        Embed a large batch asynchronously in chunks.
        """
        try:
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embeddings = await self.embed(batch, batch_size=len(batch))
                embeddings.extend(batch_embeddings)
                
                # Yield control to allow other tasks
                await asyncio.sleep(0)
            
            return embeddings
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise
    
    def get_embedding_dimension(self) -> int:
        """Get embedding dimension."""
        if self._model is None:
            # Return default for known models
            if "all-MiniLM" in self.model_name:
                return 384
            elif "all-mpnet" in self.model_name:
                return 768
            else:
                return 384
        return self._model.get_sentence_embedding_dimension()
