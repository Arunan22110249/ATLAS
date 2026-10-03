"""
Rate limiting middleware.
"""


import redis.asyncio as redis
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting middleware."""
    
    def __init__(self, app, redis_client: redis.Redis, requests_per_minute: int = 60):
        super().__init__(app)
        self.redis = redis_client
        self.rpm = requests_per_minute
        self.tokens_per_second = requests_per_minute / 60.0
    
    async def dispatch(self, request: Request, call_next):
        """Rate limit based on user/IP."""
        # Get identifier (user ID or IP)
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            # Fall back to IP address
            forwarded_for = request.headers.get("X-Forwarded-For")
            user_id = forwarded_for.split(",")[0] if forwarded_for else request.client.host
        
        key = f"rate_limit:{user_id}"
        
        # Get current token count
        current = await self.redis.get(key)
        if current is None:
            tokens = self.rpm
            ttl = 60
        else:
            tokens = int(current)
            ttl = await self.redis.ttl(key)
        
        # Check if request is allowed
        if tokens <= 0:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {self.rpm} requests per minute."
            )
        
        # Consume token
        tokens -= 1
        await self.redis.setex(key, 60, tokens)
        
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(tokens)
        
        return response


class CORSMiddleware(BaseHTTPMiddleware):
    """Custom CORS middleware with flexible configuration."""
    
    def __init__(
        self,
        app,
        allow_origins: list[str],
        allow_methods: list[str] = None,
        allow_headers: list[str] = None,
        allow_credentials: bool = True,
        max_age: int = 600
    ):
        super().__init__(app)
        self.allow_origins = allow_origins
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.max_age = max_age
    
    async def dispatch(self, request: Request, call_next):
        """Handle CORS headers."""
        origin = request.headers.get("origin")
        
        # Check if origin is allowed
        if origin in self.allow_origins or "*" in self.allow_origins:
            if request.method == "OPTIONS":
                return self._build_cors_response()
            
            response = await call_next(request)
            self._add_cors_headers(response, origin)
            return response
        
        return await call_next(request)
    
    def _build_cors_response(self):
        """Build CORS preflight response."""
        from starlette.responses import Response
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": ", ".join(self.allow_origins),
                "Access-Control-Allow-Methods": ", ".join(self.allow_methods),
                "Access-Control-Allow-Headers": ", ".join(self.allow_headers),
                "Access-Control-Max-Age": str(self.max_age),
            }
        )
    
    def _add_cors_headers(self, response, origin: str):
        """Add CORS headers to response."""
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = str(self.allow_credentials).lower()
        response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request ID to all requests."""
    
    async def dispatch(self, request: Request, call_next):
        """Add request ID."""
        import uuid
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Global error handling middleware."""
    
    async def dispatch(self, request: Request, call_next):
        """Handle errors gracefully."""
        try:
            response = await call_next(request)
            return response
        except ValueError as e:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={
                    "detail": str(e),
                    "error_type": "validation_error"
                }
            )
        except Exception as e:
            import logging

            from starlette.responses import JSONResponse
            logging.error(f"Unhandled error: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "error_type": "internal_error"
                }
            )
