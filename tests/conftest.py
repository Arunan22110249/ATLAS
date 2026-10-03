"""
Pytest configuration and fixtures.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import Settings
from backend.models import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_session():
    """Create async session for tests."""
    # Use in-memory SQLite for tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        yield session
        await session.close()
    
    await engine.dispose()


@pytest.fixture
def test_settings():
    """Provide test settings."""
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/1",  # Use different DB for testing
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
    )


@pytest.fixture
async def redis_client():
    """Provide mock Redis client for tests."""
    import time
    
    # Create a mock Redis client with in-memory storage and TTL support
    mock_redis = AsyncMock()
    mock_redis._store = {}  # {key: (value, expiration_time)}
    
    async def mock_set(key: str, value: str, ex: int = None):
        mock_redis._store[key] = (value, None)
        return True
    
    async def mock_get(key: str):
        if key not in mock_redis._store:
            return None
        value, expiration = mock_redis._store[key]
        # Check if expired
        if expiration and time.time() >= expiration:
            del mock_redis._store[key]
            return None
        return value
    
    async def mock_setex(key: str, seconds: int, value: str):
        expiration_time = time.time() + seconds
        mock_redis._store[key] = (value, expiration_time)
        return True
    
    async def mock_keys(pattern: str):
        current_time = time.time()
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            result = []
            for key in mock_redis._store:
                if key.startswith(prefix):
                    value, expiration = mock_redis._store[key]
                    # Include only non-expired keys
                    if not expiration or current_time < expiration:
                        result.append(key)
                    else:
                        # Clean up expired key
                        del mock_redis._store[key]
            return result
        return []
    
    async def mock_delete(*keys):
        count = 0
        for key in keys:
            if key in mock_redis._store:
                del mock_redis._store[key]
                count += 1
        return count
    
    async def mock_exists(*keys):
        count = 0
        current_time = time.time()
        for key in keys:
            if key in mock_redis._store:
                value, expiration = mock_redis._store[key]
                if not expiration or current_time < expiration:
                    count += 1
        return count
    
    async def mock_clear():
        mock_redis._store.clear()
        return True
    
    async def mock_info(section=None):
        return {}
    
    mock_redis.set = mock_set
    mock_redis.get = mock_get
    mock_redis.setex = mock_setex
    mock_redis.keys = mock_keys
    mock_redis.delete = mock_delete
    mock_redis.exists = mock_exists
    mock_redis.flushdb = mock_clear
    mock_redis.info = mock_info
    
    return mock_redis


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


# Async marker
pytestmark = pytest.mark.asyncio
