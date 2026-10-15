import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.base import LLMInvalidResponse, LLMModelMissing, LLMTimeout, LLMUnavailable
from app.llm.factory import get_llm_service
from app.llm.ollama import OllamaService
from app.main import app


def service_with(handler):
    client = httpx.Client(base_url="http://ollama:11434", transport=httpx.MockTransport(handler))
    service = OllamaService("http://ollama:11434", "llama3.2:3b", 10, 2, 128, client=client)
    return service, client


def call_api(service, method: str, path: str, **kwargs):
    app.dependency_overrides[get_llm_service] = lambda: service
    try:
        with TestClient(app) as client:
            return client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.pop(get_llm_service, None)


def test_generation_calls_ollama_with_only_the_prompt():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        assert json.loads(request.content) == {
            "model": "llama3.2:3b",
            "prompt": "Explain what machine learning is in one sentence.",
            "stream": False,
            "options": {"num_predict": 128},
        }
        return httpx.Response(200, json={"response": "Machine learning learns patterns from data.", "done": True})

    service, client = service_with(handler)
    try:
        response = call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "  Explain what machine learning is in one sentence.  "})
        assert response.status_code == 200
        assert response.json() == {"response": "Machine learning learns patterns from data.", "model": "llama3.2:3b"}
    finally:
        client.close()


def test_structured_generation_sends_schema_and_validates_json():
    schema = {"type": "object", "properties": {"answerable": {"type": "boolean"}}, "required": ["answerable"]}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["format"] == schema
        assert body["options"] == {"num_predict": 128, "temperature": 0}
        return httpx.Response(200, json={"response": '{"answerable": true}', "done": True})

    service, client = service_with(handler)
    try:
        assert service.generate_structured("Answer from evidence", schema) == {"answerable": True}
    finally:
        client.close()


def test_structured_generation_rejects_invalid_json():
    service, client = service_with(lambda _request: httpx.Response(200, json={"response": "not json", "done": True}))
    try:
        with pytest.raises(LLMInvalidResponse):
            service.generate_structured("Question", {"type": "object"})
    finally:
        client.close()


def test_chat_with_tools_uses_ollama_chat_protocol():
    tools = [{"type": "function", "function": {"name": "search_documents", "parameters": {"type": "object"}}}]
    messages = [{"role": "user", "content": "Find the budget"}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["messages"] == messages
        assert body["tools"] == tools
        assert body["options"] == {"num_predict": 128, "temperature": 0}
        return httpx.Response(200, json={"message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "search_documents", "arguments": {"query": "budget"}}}],
        }})

    service, client = service_with(handler)
    try:
        message = service.chat_with_tools(messages, tools)
        assert message["tool_calls"][0]["function"]["name"] == "search_documents"
    finally:
        client.close()


def test_chat_with_tools_rejects_invalid_tool_call():
    service, client = service_with(lambda _request: httpx.Response(200, json={
        "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"arguments": {}}}]}
    }))
    try:
        with pytest.raises(LLMInvalidResponse):
            service.chat_with_tools([{"role": "user", "content": "Hello"}], [{"type": "function"}])
    finally:
        client.close()


def test_empty_prompt_is_rejected_before_calling_ollama():
    service, client = service_with(lambda _request: pytest.fail("Ollama must not be called"))
    try:
        assert call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "  "}).status_code == 422
    finally:
        client.close()


def test_status_reports_installed_model():
    service, client = service_with(lambda _request: httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]}))
    try:
        response = call_api(service, "GET", "/api/v1/llm/status")
        assert response.json() == {"status": "available", "provider": "ollama", "model": "llama3.2:3b"}
    finally:
        client.close()


def test_status_reports_missing_model():
    service, client = service_with(lambda _request: httpx.Response(200, json={"models": []}))
    try:
        assert call_api(service, "GET", "/api/v1/llm/status").json()["status"] == "model_missing"
    finally:
        client.close()


def test_ollama_unavailable_does_not_crash_backend():
    def unavailable(_request):
        raise httpx.ConnectError("connection refused")

    service, client = service_with(unavailable)
    try:
        assert service.status() == "unavailable"
        response = call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "Hello"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Ollama is unavailable"}
        assert call_api(service, "GET", "/health").status_code == 200
    finally:
        client.close()


def test_missing_model_is_reported():
    service, client = service_with(lambda _request: httpx.Response(404, json={"error": "model not found"}))
    try:
        with pytest.raises(LLMModelMissing):
            service.generate("Hello")
        assert call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "Hello"}).status_code == 503
    finally:
        client.close()


def test_generation_timeout_is_reported():
    def timeout(_request):
        raise httpx.ReadTimeout("slow model")

    service, client = service_with(timeout)
    try:
        with pytest.raises(LLMTimeout):
            service.generate("Hello")
        assert call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "Hello"}).status_code == 504
    finally:
        client.close()


@pytest.mark.parametrize("body", ["not-json", '{"done":false,"response":"partial"}', '{"done":true,"response":"  "}'])
def test_invalid_model_response_is_reported(body):
    service, client = service_with(lambda _request: httpx.Response(200, text=body))
    try:
        with pytest.raises(LLMInvalidResponse):
            service.generate("Hello")
        assert call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "Hello"}).status_code == 502
    finally:
        client.close()


def test_generation_error_is_reported():
    service, client = service_with(lambda _request: httpx.Response(500, json={"error": "generation failed"}))
    try:
        assert call_api(service, "POST", "/api/v1/llm/generate", json={"prompt": "Hello"}).status_code == 502
    finally:
        client.close()
