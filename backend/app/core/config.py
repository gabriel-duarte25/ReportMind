from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    database_url: str | None = None
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "reportmind"
    mysql_user: str = "reportmind"
    mysql_password: str | None = None
    frontend_origin: str = "http://localhost:3000"
    log_level: str = "INFO"
    document_storage_path: Path = Path("/data/documents")
    max_upload_size_mb: int = Field(default=25, gt=0, le=1024)
    chunk_size_chars: int = Field(default=1200, ge=100, le=10000)
    chunk_overlap_chars: int = Field(default=150, ge=0, le=3000)
    processing_stale_minutes: int = Field(default=30, ge=1, le=1440)
    indexing_stale_minutes: int = Field(default=60, ge=1, le=1440)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "reportmind_chunks_e5_small_v1"
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_dimension: int = Field(default=384, gt=0)
    embedding_cache_path: Path = Path("/models")
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: int = Field(default=180, ge=1, le=900)
    ollama_status_timeout_seconds: int = Field(default=5, ge=1, le=60)
    ollama_num_predict: int = Field(default=512, ge=1, le=4096)
    rag_top_k: int = Field(default=4, ge=1, le=10)
    rag_max_context_chars: int = Field(default=6000, ge=500, le=12000)
    rag_min_score: float = Field(default=0.78, ge=0, le=1)
    rag_retrieval_mode: Literal["vector", "hybrid"] = "hybrid"
    rag_vector_pool_size: int = Field(default=20, ge=1, le=100)
    rag_bm25_pool_size: int = Field(default=20, ge=1, le=100)
    rag_rrf_k: int = Field(default=60, ge=1, le=1000)
    agent_max_iterations: int = Field(default=6, ge=1, le=12)
    agent_max_tool_calls: int = Field(default=10, ge=1, le=30)
    agent_search_limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS must be smaller than CHUNK_SIZE_CHARS")
        return self

    @property
    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        if not self.mysql_password:
            raise ValueError("MYSQL_PASSWORD is required when DATABASE_URL is not set")
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
