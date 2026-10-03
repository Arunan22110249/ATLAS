"""
ATLAS - Multi-Tenant Enterprise RAG & Knowledge Intelligence Platform

Configuration module with environment-based settings.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    # Application
    app_name: str = "ATLAS"
    app_version: str = "1.0.0"
    environment: str = Field(default="development", validation_alias="ENV")
    debug: bool = False
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    
    # JWT
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://atlas:atlas@localhost:5432/atlas",
        validation_alias="DATABASE_URL"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False
    
    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL"
    )
    redis_timeout: int = 30
    
    # Kafka
    kafka_brokers: str = Field(
        default="localhost:9092",
        validation_alias="KAFKA_BROKERS"
    )
    kafka_consumer_group: str = "atlas-workers"
    kafka_max_batch_size: int = 100
    kafka_session_timeout_ms: int = 30000
    
    # Object Storage (MinIO/S3)
    storage_url: str = Field(
        default="http://localhost:9000",
        validation_alias="STORAGE_URL"
    )
    storage_access_key: str = Field(default="minioadmin")
    storage_secret_key: str = Field(default="minioadmin")
    storage_bucket: str = "atlas-documents"
    storage_use_ssl: bool = False
    
    # Qdrant
    qdrant_url: str = Field(
        default="http://localhost:6333",
        validation_alias="QDRANT_URL"
    )
    qdrant_collection: str = "atlas-vectors"
    qdrant_vector_size: int = 384  # Sentence Transformers default
    qdrant_timeout: int = 30
    
    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    embedding_max_retries: int = 3
    embedding_timeout: int = 60
    
    # LLM
    llm_provider: str = "openai"  # openai, azure_openai, anthropic
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2000
    llm_timeout: int = 60
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    
    # Azure OpenAI (if using)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    
    # Reranker
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    reranker_top_k: int = 5
    reranker_timeout: int = 30
    
    # RAG
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 50
    rag_retrieval_top_k: int = 10
    rag_context_length_tokens: int = 4000
    rag_min_confidence_score: float = 0.3
    
    # Caching
    semantic_cache_ttl_seconds: int = 86400  # 24 hours
    enable_semantic_cache: bool = True
    
    # Rate limiting
    rate_limit_auth_requests: int = 100
    rate_limit_auth_window_seconds: int = 3600
    rate_limit_api_requests: int = 1000
    rate_limit_api_window_seconds: int = 3600
    
    # Document processing
    max_document_size_mb: int = 100
    allowed_document_types: str = "pdf,docx,txt,md,html,csv,json"
    document_processing_timeout: int = 300
    
    # Workers
    worker_concurrency: int = 4
    worker_log_level: str = "INFO"
    
    # Observability
    enable_otel: bool = True
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    log_level: str = "INFO"
    structured_logging: bool = True
    
    # Security
    cors_origins: str = "*"
    password_min_length: int = 8
    password_require_special: bool = True
    
    # Monitoring
    prometheus_port: int = 9090
    enable_health_check: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
