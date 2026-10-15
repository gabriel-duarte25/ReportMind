"""Ollama implementation of the provider-independent LLM service."""

import json
from typing import Any

import httpx

from app.llm.base import (
    LLMGenerationError,
    LLMInvalidResponse,
    LLMModelMissing,
    LLMService,
    LLMStatus,
    LLMTimeout,
    LLMUnavailable,
)


class OllamaService(LLMService):
    provider = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int,
        status_timeout_seconds: int,
        num_predict: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.status_timeout_seconds = status_timeout_seconds
        self.num_predict = num_predict
        self.client = client or httpx.Client(base_url=base_url.rstrip("/"))

    def status(self) -> LLMStatus:
        try:
            response = self.client.get("/api/tags", timeout=self.status_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            models = payload["models"]
            if not isinstance(models, list):
                return "unavailable"
            for item in models:
                if isinstance(item, dict) and (item.get("name") == self.model or item.get("model") == self.model):
                    return "available"
            return "model_missing"
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return "unavailable"

    def generate(self, prompt: str) -> str:
        return self._generate(prompt)

    def generate_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            result = json.loads(self._generate(prompt, schema))
        except ValueError as exc:
            raise LLMInvalidResponse("Ollama returned invalid structured JSON") from exc
        if not isinstance(result, dict):
            raise LLMInvalidResponse("Ollama returned an invalid structured response")
        return result

    def chat_with_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": self.num_predict, "temperature": 0},
        }
        if tools:
            body["tools"] = tools
        payload = self._post("/api/chat", body)
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            raise LLMInvalidResponse("Ollama returned an invalid chat message")
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        if not isinstance(content, str) or not isinstance(tool_calls, list):
            raise LLMInvalidResponse("Ollama returned invalid chat fields")
        if not content.strip() and not tool_calls:
            raise LLMInvalidResponse("Ollama returned an empty chat message")
        for call in tool_calls:
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                raise LLMInvalidResponse("Ollama returned an invalid tool call")
            arguments = function.get("arguments", {})
            if not isinstance(arguments, (dict, str)):
                raise LLMInvalidResponse("Ollama returned invalid tool arguments")
        return {"role": "assistant", "content": content, "tool_calls": tool_calls}

    def _generate(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": self.num_predict},
        }
        if schema is not None:
            body["format"] = schema
            body["options"]["temperature"] = 0
        payload = self._post("/api/generate", body)

        if not isinstance(payload, dict) or payload.get("done") is not True:
            raise LLMInvalidResponse("Ollama returned an incomplete response")
        content = payload.get("response")
        if not isinstance(content, str) or not content.strip():
            raise LLMInvalidResponse("Ollama returned an empty response")
        return content.strip()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.post(path, json=body, timeout=self.timeout_seconds)
            if response.status_code == 404:
                raise LLMModelMissing("Configured Ollama model is not installed")
            response.raise_for_status()
            payload = response.json()
        except LLMModelMissing:
            raise
        except httpx.TimeoutException as exc:
            raise LLMTimeout("Ollama generation timed out") from exc
        except httpx.ConnectError as exc:
            raise LLMUnavailable("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMGenerationError("Ollama could not generate a response") from exc
        except httpx.RequestError as exc:
            raise LLMUnavailable("Ollama is unavailable") from exc
        except ValueError as exc:
            raise LLMInvalidResponse("Ollama returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise LLMInvalidResponse("Ollama returned an invalid response")
        return payload
