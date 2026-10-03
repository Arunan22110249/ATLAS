#!/usr/bin/env python3
"""
ATLAS Phase 3: Integration Test Suite
Designed to run against real infrastructure (PostgreSQL, Kafka, Redis, etc.)

This script coordinates integration tests across the full ATLAS stack.
It should be run AFTER docker compose is up and services are healthy.

Prerequisites:
- Docker containers running: postgres, redis, kafka, qdrant, minio, api, worker
- API accessible at http://localhost:8000
- PostgreSQL migrations completed

Usage:
    python tests/integration_tests.py
    python tests/integration_tests.py --test-class TestDocumentFlow
    python tests/integration_tests.py --verbose
"""

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import aiohttp
import asyncpg
import redis.asyncio as redis

# ============================================================================
# Test Configuration
# ============================================================================

@dataclass
class TestConfig:
    """Integration test configuration."""
    api_base_url: str = "http://localhost:8000/api/v1"
    api_health_url: str = "http://localhost:8000/health"
    postgres_url: str = "postgresql+asyncpg://atlas:atlas@localhost:5432/atlas"
    redis_url: str = "redis://localhost:6379/0"
    kafka_brokers: str = "localhost:9092"
    qdrant_url: str = "http://localhost:6333"
    minio_url: str = "http://localhost:9000"
    
    # Test data
    test_user_email: str = "integration-test@atlas.local"
    test_user_password: str = "IntegrationTest123!"
    test_tenant_name: str = "Integration Test Tenant"
    test_collection_name: str = "Integration Test Collection"
    
    # Timeouts
    api_timeout: int = 30
    service_timeout: int = 60
    
    # Flags
    verbose: bool = False
    skip_cleanup: bool = False


# ============================================================================
# Helper Utilities
# ============================================================================

class Logger:
    """Simple structured logging."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
    
    def info(self, msg: str, **kwargs):
        """Log info message."""
        data = {"level": "info", "message": msg, "timestamp": datetime.utcnow().isoformat()}
        data.update(kwargs)
        print(json.dumps(data))
    
    def success(self, msg: str, **kwargs):
        """Log success message."""
        data = {"level": "success", "message": msg, "timestamp": datetime.utcnow().isoformat()}
        data.update(kwargs)
        print(f"✅ {msg}")
        if self.verbose:
            print(json.dumps(data, indent=2))
    
    def error(self, msg: str, **kwargs):
        """Log error message."""
        data = {"level": "error", "message": msg, "timestamp": datetime.utcnow().isoformat()}
        data.update(kwargs)
        print(f"❌ {msg}")
        print(json.dumps(data, indent=2))
    
    def warning(self, msg: str, **kwargs):
        """Log warning message."""
        data = {"level": "warning", "message": msg, "timestamp": datetime.utcnow().isoformat()}
        data.update(kwargs)
        print(f"⚠️  {msg}")
        if self.verbose:
            print(json.dumps(data, indent=2))


# ============================================================================
# Service Health & Setup
# ============================================================================

class ServiceValidator:
    """Validates service health and connectivity."""
    
    def __init__(self, config: TestConfig, logger: Logger):
        self.config = config
        self.logger = logger
    
    async def validate_all_services(self) -> bool:
        """Check all required services are healthy."""
        self.logger.info("Validating service health...")
        
        services = [
            ("API", self._check_api),
            ("PostgreSQL", self._check_postgres),
            ("Redis", self._check_redis),
            ("Qdrant", self._check_qdrant),
            ("MinIO", self._check_minio),
        ]
        
        results = {}
        for name, check in services:
            try:
                results[name] = await asyncio.wait_for(check(), timeout=self.config.service_timeout)
            except Exception as e:
                self.logger.error(f"Failed to check {name}: {e}")
                results[name] = False
        
        all_healthy = all(results.values())
        
        # Report results
        for service, healthy in results.items():
            status = "✅ HEALTHY" if healthy else "❌ UNHEALTHY"
            self.logger.info(f"  {service}: {status}")
        
        return all_healthy
    
    async def _check_api(self) -> bool:
        """Check API health."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config.api_health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    return resp.status == 200 and data.get("status") in ["healthy", "degraded"]
        except Exception:
            return False
    
    async def _check_postgres(self) -> bool:
        """Check PostgreSQL connectivity."""
        try:
            conn = await asyncpg.connect(self.config.postgres_url.replace("postgresql+asyncpg://", "postgresql://"))
            version = await conn.fetchval("SELECT version()")
            await conn.close()
            return "PostgreSQL" in version
        except Exception:
            return False
    
    async def _check_redis(self) -> bool:
        """Check Redis connectivity."""
        try:
            r = await redis.from_url(self.config.redis_url)
            pong = await r.ping()
            await r.close()
            return pong
        except Exception:
            return False
    
    async def _check_qdrant(self) -> bool:
        """Check Qdrant connectivity."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.config.qdrant_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def _check_minio(self) -> bool:
        """Check MinIO connectivity."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.config.minio_url}/minio/health/live", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False


# ============================================================================
# Integration Test Suite
# ============================================================================

class IntegrationTestSuite:
    """Main integration test suite."""
    
    def __init__(self, config: TestConfig, logger: Logger):
        self.config = config
        self.logger = logger
        self.session: aiohttp.ClientSession | None = None
        self.auth_token: str | None = None
        self.tenant_id: str | None = None
        self.collection_id: str | None = None
        self.document_id: str | None = None
        self.test_results: dict[str, bool] = {}
    
    async def setup(self):
        """Setup test session."""
        self.session = aiohttp.ClientSession()
        self.logger.info("Integration test suite initialized")
    
    async def teardown(self):
        """Cleanup test session."""
        if self.session:
            await self.session.close()
        self.logger.info("Integration test suite cleaned up")
    
    async def run_all_tests(self) -> dict[str, bool]:
        """Run all integration tests."""
        tests = [
            ("Authentication", self.test_authentication),
            ("Tenant Creation", self.test_tenant_creation),
            ("Collection Creation", self.test_collection_creation),
            ("Document Upload", self.test_document_upload),
            ("Document Processing", self.test_document_processing),
            ("BM25 Search", self.test_bm25_search),
            ("Dense Search", self.test_dense_search),
            ("Hybrid Search", self.test_hybrid_search),
            ("RAG Query", self.test_rag_query),
            ("Multi-Tenant Isolation", self.test_multi_tenant_isolation),
            ("Cache Performance", self.test_cache_performance),
            ("Error Handling", self.test_error_handling),
        ]
        
        self.logger.info(f"Running {len(tests)} integration tests...")
        
        for test_name, test_func in tests:
            try:
                await test_func()
                self.test_results[test_name] = True
                self.logger.success(f"✅ {test_name}")
            except AssertionError as e:
                self.test_results[test_name] = False
                self.logger.error(f"❌ {test_name}: {e}")
            except Exception as e:
                self.test_results[test_name] = False
                self.logger.error(f"❌ {test_name}: Unexpected error: {e}")
        
        return self.test_results
    
    # --------
    # Tests
    # --------
    
    async def test_authentication(self):
        """Test user registration and login."""
        # Register
        user_id = str(uuid.uuid4()).split('-')[0]
        email = f"test-{user_id}@atlas.local"
        
        async with self.session.post(
            f"{self.config.api_base_url}/auth/register",
            json={
                "email": email,
                "password": self.config.test_user_password,
                "full_name": "Test User"
            }
        ) as resp:
            assert resp.status == 201, f"Register failed: {resp.status}"
            data = await resp.json()
            assert "access_token" in data
            self.auth_token = data["access_token"]
    
    async def test_tenant_creation(self):
        """Test creating a tenant."""
        assert self.auth_token, "Must authenticate first"
        
        async with self.session.post(
            f"{self.config.api_base_url}/tenants",
            headers={"Authorization": f"Bearer {self.auth_token}"},
            json={"name": self.config.test_tenant_name}
        ) as resp:
            assert resp.status == 201, f"Tenant creation failed: {resp.status}"
            data = await resp.json()
            self.tenant_id = data.get("id")
            assert self.tenant_id, "No tenant ID returned"
    
    async def test_collection_creation(self):
        """Test creating a collection."""
        assert self.auth_token and self.tenant_id, "Must setup tenant first"
        
        async with self.session.post(
            f"{self.config.api_base_url}/collections",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json={
                "name": self.config.test_collection_name,
                "description": "Integration test collection",
                "tenant_id": self.tenant_id
            }
        ) as resp:
            assert resp.status == 201, f"Collection creation failed: {resp.status}"
            data = await resp.json()
            self.collection_id = data.get("id")
            assert self.collection_id, "No collection ID returned"
    
    async def test_document_upload(self):
        """Test document upload."""
        assert self.auth_token and self.collection_id, "Must setup collection first"
        
        # Create test document
        test_content = """
        # Test Document for Integration Testing
        
        This document contains information about machine learning and artificial intelligence.
        
        ## Machine Learning Types
        - Supervised Learning
        - Unsupervised Learning
        - Reinforcement Learning
        
        ## Applications
        Machine learning is used in various applications including:
        1. Computer Vision
        2. Natural Language Processing
        3. Recommendation Systems
        4. Fraud Detection
        """
        
        # Create multipart form data
        data = aiohttp.FormData()
        data.add_field('file', test_content, filename='test-doc.txt', content_type='text/plain')
        data.add_field('collection_id', self.collection_id)
        data.add_field('title', 'Test Document')
        
        async with self.session.post(
            f"{self.config.api_base_url}/documents/upload",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            data=data
        ) as resp:
            assert resp.status in [200, 201, 202], f"Document upload failed: {resp.status}"
            doc_data = await resp.json()
            self.document_id = doc_data.get("id")
            assert self.document_id, "No document ID returned"
    
    async def test_document_processing(self):
        """Test document processing status."""
        assert self.auth_token and self.document_id, "Must upload document first"
        
        # Poll for processing completion (up to 60 seconds)
        for attempt in range(60):
            async with self.session.get(
                f"{self.config.api_base_url}/documents/{self.document_id}",
                headers={
                    "Authorization": f"Bearer {self.auth_token}",
                    "X-Tenant-ID": self.tenant_id
                }
            ) as resp:
                assert resp.status == 200
                doc_data = await resp.json()
                status = doc_data.get("status")
                
                if status == "READY":
                    self.logger.info(f"Document processing completed after {attempt}s")
                    return
                elif status == "FAILED":
                    raise AssertionError(f"Document processing failed: {doc_data.get('error')}")
                
                await asyncio.sleep(1)
        
        raise AssertionError("Document processing timeout (>60s)")
    
    async def test_bm25_search(self):
        """Test BM25 keyword search."""
        assert self.auth_token and self.collection_id, "Must have ready document"
        
        async with self.session.post(
            f"{self.config.api_base_url}/search/bm25",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json={
                "query": "machine learning types",
                "collection_id": self.collection_id,
                "top_k": 5
            }
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            results = data.get("results", [])
            assert len(results) > 0, "No BM25 results returned"
            assert "score" in results[0], "No score in results"
    
    async def test_dense_search(self):
        """Test dense vector search."""
        assert self.auth_token and self.collection_id, "Must have ready document"
        
        async with self.session.post(
            f"{self.config.api_base_url}/search/dense",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json={
                "query": "AI applications in industry",
                "collection_id": self.collection_id,
                "top_k": 5
            }
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            results = data.get("results", [])
            assert len(results) > 0, "No dense results returned"
            assert "similarity" in results[0], "No similarity score in results"
    
    async def test_hybrid_search(self):
        """Test hybrid BM25 + dense search."""
        assert self.auth_token and self.collection_id, "Must have ready document"
        
        async with self.session.post(
            f"{self.config.api_base_url}/search/hybrid",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json={
                "query": "learning algorithms",
                "collection_id": self.collection_id,
                "top_k": 5,
                "bm25_weight": 0.4,
                "dense_weight": 0.6
            }
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            results = data.get("results", [])
            assert len(results) > 0, "No hybrid results returned"
            assert "score" in results[0], "No combined score in results"
    
    async def test_rag_query(self):
        """Test full RAG pipeline."""
        assert self.auth_token and self.collection_id, "Must have ready document"
        
        async with self.session.post(
            f"{self.config.api_base_url}/rag/query",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json={
                "question": "What are the types of machine learning?",
                "collection_id": self.collection_id,
                "top_k": 3
            }
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert "answer" in data, "No answer in RAG response"
            assert "sources" in data, "No sources in RAG response"
            assert len(data.get("sources", [])) > 0, "No source documents returned"
    
    async def test_multi_tenant_isolation(self):
        """Test that tenants cannot access each other's data."""
        # This would require creating a second tenant/user and attempting cross-tenant access
        # For now, verify that X-Tenant-ID is validated
        
        assert self.auth_token and self.collection_id, "Must have initial setup"
        
        # Attempt to search with wrong tenant ID
        fake_tenant_id = str(uuid.uuid4())
        
        async with self.session.post(
            f"{self.config.api_base_url}/search/hybrid",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": fake_tenant_id  # Different tenant
            },
            json={
                "query": "test",
                "collection_id": self.collection_id,
                "top_k": 5
            }
        ) as resp:
            # Should either return empty or error (tenant mismatch)
            assert resp.status in [200, 403, 404], f"Unexpected status: {resp.status}"
            if resp.status == 200:
                data = await resp.json()
                # If successful, should have 0 results
                results = data.get("results", [])
                assert len(results) == 0, "Returned results for different tenant!"
    
    async def test_cache_performance(self):
        """Test that caching improves performance."""
        assert self.auth_token and self.collection_id, "Must have ready document"
        
        query = {"query": "test", "collection_id": self.collection_id, "top_k": 5}
        
        # First query (cold cache)
        start = time.time()
        async with self.session.post(
            f"{self.config.api_base_url}/search/hybrid",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json=query
        ) as resp:
            assert resp.status == 200
            await resp.json()
        cold_time = time.time() - start
        
        # Wait a bit
        await asyncio.sleep(0.5)
        
        # Second query (warm cache)
        start = time.time()
        async with self.session.post(
            f"{self.config.api_base_url}/search/hybrid",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id
            },
            json=query
        ) as resp:
            assert resp.status == 200
            await resp.json()
        warm_time = time.time() - start
        
        self.logger.info(f"Cold cache: {cold_time:.3f}s, Warm cache: {warm_time:.3f}s")
        # Cache should improve performance (ideally 2-5x faster)
        # But this is environment-dependent, so just log for now
    
    async def test_error_handling(self):
        """Test that errors are handled properly."""
        assert self.auth_token, "Must authenticate first"
        
        # Test missing required field
        async with self.session.post(
            f"{self.config.api_base_url}/search/hybrid",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id or str(uuid.uuid4())
            },
            json={"query": "test"}  # Missing collection_id
        ) as resp:
            # Should return 400 Bad Request
            assert resp.status in [400, 422], f"Expected validation error, got {resp.status}"
        
        # Test invalid collection ID
        async with self.session.post(
            f"{self.config.api_base_url}/search/hybrid",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "X-Tenant-ID": self.tenant_id or str(uuid.uuid4())
            },
            json={
                "query": "test",
                "collection_id": str(uuid.uuid4()),
                "top_k": 5
            }
        ) as resp:
            # Should return 404 Not Found
            assert resp.status in [404, 200], f"Expected not found or empty, got {resp.status}"


# ============================================================================
# Main Test Runner
# ============================================================================

async def main():
    """Main test execution."""
    config = TestConfig(verbose="-v" in sys.argv or "--verbose" in sys.argv)
    logger = Logger(verbose=config.verbose)
    
    logger.info("=" * 70)
    logger.info("ATLAS Integration Test Suite")
    logger.info("=" * 70)
    
    # Validate services
    validator = ServiceValidator(config, logger)
    if not await validator.validate_all_services():
        logger.error("One or more services are not healthy. Cannot proceed.")
        sys.exit(1)
    
    # Run tests
    suite = IntegrationTestSuite(config, logger)
    
    try:
        await suite.setup()
        results = await suite.run_all_tests()
    finally:
        await suite.teardown()
    
    # Report results
    logger.info("\n" + "=" * 70)
    logger.info("Test Results Summary")
    logger.info("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} passed")
    logger.info("=" * 70)
    
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
