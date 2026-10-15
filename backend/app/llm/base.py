"""Provider-independent interface and errors for simple text generation."""

from abc import ABC, abstractmethod
from typing import Any, Literal


LLMStatus = Literal["available", "model_missing", "unavailable"]


class LLMError(Exception):
    """A provider failed without affecting the rest of the application."""


class LLMUnavailable(LLMError):
    pass


class LLMModelMissing(LLMError):
    pass


class LLMTimeout(LLMError):
    pass


class LLMInvalidResponse(LLMError):
    pass


class LLMGenerationError(LLMError):
    pass


class LLMService(ABC):
    provider: str
    model: str

    @abstractmethod
    def status(self) -> LLMStatus:
        """Report whether the configured model is ready."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate text from only the supplied prompt."""

    @abstractmethod
    def generate_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate a JSON object conforming to the supplied schema."""

    @abstractmethod
    def chat_with_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Return one assistant message, optionally containing tool calls."""
