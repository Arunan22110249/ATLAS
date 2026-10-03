"""
Semantic caching with Redis.
"""

import hashlib
import json
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class SemanticCache:
    """Redis-based semantic cache for RAG responses."""
    
    def __init__(self, redis_url_or_client: str | object, ttl_seconds: int = 86400):
        """Initialize cache with either a redis URL string or a redis client object."""
        self.ttl_seconds = ttl_seconds
        self._redis: redis.Redis | None = None
        
        # Accept both redis_url string and redis client object
        if isinstance(redis_url_or_client, str):
            self.redis_url = redis_url_or_client
            self._redis_client = None
        else:
            # Direct redis client injection (for testing)
            self.redis_url = None
            self._redis_client = redis_url_or_client
            self._redis = redis_url_or_client
    
    async def connect(self):
        """Connect to Redis."""
        if self._redis_client:
            # Already injected, no need to connect
            return
        
        try:
            self._redis = await redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Connected to Redis cache")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._redis = None
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis and not self._redis_client:
            await self._redis.close()
    
    def _make_cache_key(self, query: str, tenant_id: str) -> str:
        """Create cache key from query and tenant."""
        # Normalize query
        normalized = query.lower().strip()
        # Hash to keep key size reasonable
        query_hash = hashlib.md5(normalized.encode()).hexdigest()
        return f"rag:cache:{tenant_id}:{query_hash}"
    
    async def get(self, tenant_id: str, query: str) -> dict | None:
        """Get cached response."""
        if not self._redis:
            return None
        
        try:
            key = self._make_cache_key(query, tenant_id)
            cached = await self._redis.get(key)
            
            if cached:
                response_data = json.loads(cached)
                logger.debug(f"Cache hit for key: {key}")
                return response_data
            
            return None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    async def set(self, tenant_id: str, query: str, response_data: dict, ttl_seconds: int | None = None):
        """Cache response."""
        if not self._redis:
            return
        
        try:
            key = self._make_cache_key(query, tenant_id)
            ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
            
            # Convert response to JSON-serializable format
            cached_response = response_data.model_dump() if hasattr(response_data, 'model_dump') else response_data
            
            await self._redis.setex(
                key,
                ttl,
                json.dumps(cached_response, default=str),
            )
            logger.debug(f"Cached response for key: {key}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    async def invalidate_by_document(self, tenant_id: str, doc_id: str | None = None):
        """Invalidate all cache entries for a tenant (when documents change)."""
        if not self._redis:
            return
        
        try:
            pattern = f"rag:cache:{tenant_id}:*"
            keys = await self._redis.keys(pattern)
            
            if keys:
                await self._redis.delete(*keys)
                logger.info(f"Invalidated {len(keys)} cache entries for tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
    
    async def clear(self, tenant_id: str | None = None):
        """Clear cache entries."""
        if not self._redis:
            return
        
        try:
            if tenant_id:
                # Clear only for specific tenant
                pattern = f"rag:cache:{tenant_id}:*"
                keys = await self._redis.keys(pattern)
            else:
                # Clear all cache
                pattern = "rag:cache:*"
                keys = await self._redis.keys(pattern)
            
            if keys:
                await self._redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries")
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
    
    async def get_stats(self) -> dict:
        """Get cache statistics."""
        if not self._redis:
            return {}
        
        try:
            pattern = "rag:cache:*"
            keys = await self._redis.keys(pattern)
            
            return {
                "total_keys": len(keys),
                "redis_connected": True,
                "ttl_seconds": self.ttl_seconds,
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"redis_connected": False}
