"""Select the configured LLM provider for API dependencies."""

from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMService
from app.llm.ollama import OllamaService


@lru_cache
def get_llm_service() -> LLMService:
    settings = get_settings()
    return OllamaService(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        status_timeout_seconds=settings.ollama_status_timeout_seconds,
        num_predict=settings.ollama_num_predict,
    )
