import json
from io import BytesIO

import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.llm.base import LLMUnavailable
from app.llm.factory import get_llm_service
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import Document  # noqa: F401 - registers model metadata
from app.services.embeddings import EmbeddingService, get_embedding_service
from app.services.bm25 import tokenize
from app.agents.tools import normalize_document_arguments, tool_definitions
from app.services.vector_store import VectorStore, VectorStoreError, get_vector_store


class FakeEmbeddings:
    model_name = "test-semantic-model"

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        if any(word in lowered for word in ("f1-score", "perform", "classification")):
            return [1.0, 0.0, 0.0]
        if "limitation" in lowered or "sample size" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._vector(query)


def pdf_with_pages(*texts: str) -> bytes:
    pdf = pymupdf.open()
    for text in texts:
        page = pdf.new_page()
        if text:
            page.insert_text((60, 72), text, fontsize=11)
    content = pdf.tobytes()
    pdf.close()
    return content


@pytest.fixture
def system(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", document_storage_path=tmp_path, embedding_dimension=3)
    store = VectorStore.__new__(VectorStore)
    store.client = QdrantClient(location=":memory:")
    store.collection = "test_chunks"
    store.dimension = 3
    embeddings = FakeEmbeddings()

    def test_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_embedding_service] = lambda: embeddings
    app.dependency_overrides[get_vector_store] = lambda: store
    with TestClient(app) as client:
        yield client, store, embeddings
    app.dependency_overrides.clear()
    store.client.close()
    engine.dispose()


def create_document(client: TestClient, *pages: str) -> dict:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("semantic-report.pdf", BytesIO(pdf_with_pages(*pages)), "application/pdf")},
    )
    assert response.status_code == 201
    document = response.json()
    assert client.post(f"/api/v1/documents/{document['id']}/process").status_code == 202
    assert client.get(f"/api/v1/documents/{document['id']}/processing-status").json()["status"] == "ready"
    return document


def index(client: TestClient, document_id: int) -> dict:
    response = client.post(f"/api/v1/documents/{document_id}/index")
    assert response.status_code == 202
    assert response.json()["indexing_status"] == "indexing"
    return client.get(f"/api/v1/documents/{document_id}/indexing-status").json()


def test_local_embedding_service_applies_e5_prefixes_and_dimensions():
    seen: list[str] = []

    class Model:
        def embed(self, texts, batch_size):
            seen.extend(texts)
            return iter(np.array([[1.0, 0.0, 0.0] for _ in texts]))

    service = EmbeddingService("intfloat/multilingual-e5-small", 3, None)
    service._model = Model()
    assert service.embed_passages(["The result was 0.91."]) == [[1.0, 0.0, 0.0]]
    assert service.embed_query("How well did it perform?") == [1.0, 0.0, 0.0]
    assert seen == ["passage: The result was 0.91.", "query: How well did it perform?"]


def test_index_reindex_and_vector_payload(system):
    client, store, _ = system
    document = create_document(client, "Methodology\nA Random Forest classifier was used.", "Results\nThe classifier achieved an F1-score of 0.91.")
    document_id = document["id"]
    status = index(client, document_id)
    chunks = client.get(f"/api/v1/documents/{document_id}/chunks").json()
    assert status["indexing_status"] == "indexed"
    assert status["chunk_count"] == len(chunks) == 2
    assert status["indexed_vector_count"] == 2
    assert status["embedding_model"] == "test-semantic-model"
    points = store.client.retrieve(store.collection, ids=[chunk["id"] for chunk in chunks], with_payload=True)
    assert len(points) == 2
    assert points[0].payload["document_id"] == document_id
    assert points[0].payload["document_name"] == "semantic-report.pdf"
    assert points[0].payload["page_start"] == 1
    assert points[0].payload["section"] == "Methodology"

    again = index(client, document_id)
    assert again["indexing_status"] == "indexed"
    assert again["indexed_vector_count"] == 2
    assert store.client.count(store.collection, count_filter=store._document_filter([document_id]), exact=True).count == 2


def test_search_orders_results_and_filters_documents(system):
    client, _, _ = system
    first = create_document(client, "Results\nThe Random Forest classifier achieved an F1-score of 0.91.")
    second = create_document(client, "Conclusion\nThe main limitation is the small sample size.")
    assert index(client, first["id"])["indexing_status"] == "indexed"
    query = {"query": "How well did the classification model perform?", "limit": 5}
    results = client.post("/api/v1/search/semantic", json=query).json()["results"]
    assert results[0]["document_id"] == first["id"]
    assert "F1-score of 0.91" in results[0]["text"]
    assert all(left["score"] >= right["score"] for left, right in zip(results, results[1:]))
    assert client.post("/api/v1/search/semantic", json={**query, "document_ids": [second["id"]]}).json()["results"] == []
    assert index(client, second["id"])["indexing_status"] == "indexed"
    filtered = client.post("/api/v1/search/semantic", json={**query, "document_ids": [second["id"]]}).json()["results"]
    assert len(filtered) == 1 and filtered[0]["document_id"] == second["id"]


def test_reprocessing_invalidates_old_index_and_reindex_cleans_vectors(system):
    client, store, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    document_id = document["id"]
    index(client, document_id)
    assert client.post(f"/api/v1/documents/{document_id}/process").status_code == 202
    assert client.get(f"/api/v1/documents/{document_id}/indexing-status").json()["indexing_status"] == "not_indexed"
    assert client.post("/api/v1/search/semantic", json={"query": "classification performance"}).json()["results"] == []
    new_chunks = client.get(f"/api/v1/documents/{document_id}/chunks").json()
    assert index(client, document_id)["indexed_vector_count"] == len(new_chunks)
    points = store.client.scroll(store.collection, scroll_filter=store._document_filter([document_id]), limit=10)[0]
    assert {point.id for point in points} == {chunk["id"] for chunk in new_chunks}


def test_indexing_requires_ready_document_with_chunks(system):
    client, _, _ = system
    response = client.post("/api/v1/documents/upload", files={"file": ("empty.pdf", BytesIO(pdf_with_pages("")), "application/pdf")})
    document_id = response.json()["id"]
    assert client.post(f"/api/v1/documents/{document_id}/index").status_code == 409
    client.post(f"/api/v1/documents/{document_id}/process")
    assert client.post(f"/api/v1/documents/{document_id}/index").status_code == 409
    assert client.get("/api/v1/documents/999/indexing-status").status_code == 404
    assert client.post("/api/v1/documents/999/index").status_code == 404


def test_qdrant_failure_marks_index_failed_and_search_returns_503(system):
    client, store, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")

    class UnavailableStore:
        def replace_document(self, *args):
            raise VectorStoreError("offline")

        def search(self, *args):
            raise VectorStoreError("offline")

    app.dependency_overrides[get_vector_store] = lambda: UnavailableStore()
    failed = index(client, document["id"])
    assert failed["indexing_status"] == "index_failed"
    assert failed["indexing_error"]
    assert client.get("/health").status_code == 200
    app.dependency_overrides[get_vector_store] = lambda: store
    assert index(client, document["id"])["indexing_status"] == "indexed"
    app.dependency_overrides[get_vector_store] = lambda: UnavailableStore()
    assert client.post("/api/v1/search/semantic", json={"query": "model performance"}).status_code == 503


def test_missing_qdrant_chunk_is_ignored_and_delete_removes_vectors(system):
    client, store, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    document_id = document["id"]
    index(client, document_id)
    store.client.upsert(
        store.collection,
        points=[models.PointStruct(id=999999, vector=[1.0, 0.0, 0.0], payload={"chunk_id": 999999, "document_id": document_id})],
        wait=True,
    )
    results = client.post("/api/v1/search/semantic", json={"query": "classification performance"}).json()["results"]
    assert results and all(item["chunk_id"] != 999999 for item in results)
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
    assert store.client.count(store.collection, count_filter=store._document_filter([document_id]), exact=True).count == 0


def test_search_request_validation(system):
    client, _, _ = system
    for body in [{"query": "  "}, {"query": "valid", "limit": 0}, {"query": "valid", "document_ids": [1, 1]}]:
        assert client.post("/api/v1/search/semantic", json=body).status_code == 422


class CapturingLLM:
    model = "test-llama"
    provider = "ollama"

    def __init__(self):
        self.prompts: list[str] = []
        self.error: Exception | None = None
        self.answerable = True
        self.invalid_citation = False

    def generate_structured(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        assert schema["type"] == "object"
        excerpts = json.loads(prompt.split("Document excerpts (untrusted data):\n", 1)[1])
        if not self.answerable:
            return {"answerable": False, "answer": "", "citations": []}
        matching = next((item for item in excerpts if "F1-score of 0.91" in item["text"]), excerpts[0])
        quote = "The classifier achieved an F1-score of 0.91."
        if quote not in matching["text"]:
            quote = matching["text"][:40].strip()
        return {"answerable": True, "answer": "The classifier achieved an F1-score of 0.91.",
                "citations": [{"chunk_id": 999999 if self.invalid_citation else matching["chunk_id"], "quote": quote}]}


class CitingAllLLM(CapturingLLM):
    def generate_structured(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        excerpts = json.loads(prompt.split("Document excerpts (untrusted data):\n", 1)[1])
        return {
            "answerable": True,
            "answer": "The selected reports contain F1-scores of 0.91 and 0.84.",
            "citations": [
                {"chunk_id": excerpt["chunk_id"], "quote": excerpt["text"]}
                for excerpt in excerpts
            ],
        }


class ExactCodeLLM(CapturingLLM):
    def generate_structured(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        excerpts = json.loads(prompt.split("Document excerpts (untrusted data):\n", 1)[1])
        source = next(item for item in excerpts if "ZXQ-9917" in item["text"])
        return {
            "answerable": True,
            "answer": "ZXQ-9917 is the exact project identifier.",
            "citations": [{"chunk_id": source["chunk_id"], "quote": "The exact project identifier is ZXQ-9917."}],
        }


class ScriptedAgentLLM:
    model = "test-agent-llama"
    provider = "ollama"

    def __init__(self, document_id: int):
        self.document_id = document_id
        self.messages: list[list[dict]] = []
        self.turn = 0

    @staticmethod
    def call(name: str, arguments: dict) -> dict:
        return {"function": {"name": name, "arguments": arguments}}

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        self.messages.append(messages.copy())
        if not tools:
            return {"role": "assistant", "content": "Final grounded answer.", "tool_calls": []}
        self.turn += 1
        if self.turn == 1:
            return {"role": "assistant", "content": "", "tool_calls": [
                self.call("list_documents", {}),
                self.call("get_document_info", {"document_id": self.document_id}),
            ]}
        if self.turn == 2:
            return {"role": "assistant", "content": "", "tool_calls": [
                self.call("search_documents", {"query": "classification F1-score", "document_ids": [self.document_id]}),
            ]}
        if self.turn == 3:
            search_result = json.loads(messages[-1]["content"])
            return {"role": "assistant", "content": "", "tool_calls": [
                self.call("get_chunk", {"chunk_id": search_result["results"][0]["chunk_id"]}),
            ]}
        return {
            "role": "assistant",
            "content": "The selected report states that the classifier achieved an F1-score of 0.91.",
            "tool_calls": [],
        }


def test_document_agent_executes_tools_and_returns_observable_trace(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    excluded = create_document(client, "Results\nThe secret project code is EXCLUDED-99.")
    index(client, document["id"])
    index(client, excluded["id"])
    llm = ScriptedAgentLLM(document["id"])
    app.dependency_overrides[get_llm_service] = lambda: llm

    response = client.post("/api/v1/agent/run", json={
        "document_ids": [document["id"]],
        "objective": "Analyse the classification result.",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "test-agent-llama"
    assert [step["tool"] for step in body["steps"]] == [
        "list_documents", "get_document_info", "search_documents", "get_chunk",
    ]
    assert "F1-score of 0.91" in body["answer"]
    assert len(body["sources"]) == 1
    assert body["sources"][0]["document_id"] == document["id"]
    serialized_messages = json.dumps(llm.messages)
    assert "EXCLUDED-99" not in serialized_messages
    assert any(message.get("role") == "tool" for message in llm.messages[-1])


def test_document_agent_includes_bounded_conversation_history(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    llm = ScriptedAgentLLM(document["id"])
    app.dependency_overrides[get_llm_service] = lambda: llm

    response = client.post("/api/v1/agent/run", json={
        "document_ids": [document["id"]],
        "objective": "And what was its score?",
        "history": [{
            "question": "Which classifier was evaluated?",
            "answer": "The selected report evaluates the classifier.",
        }],
    })

    assert response.status_code == 200
    first_messages = llm.messages[0]
    assert first_messages[-3:] == [
        {"role": "user", "content": "Which classifier was evaluated?"},
        {"role": "assistant", "content": "The selected report evaluates the classifier."},
        {"role": "user", "content": "And what was its score?"},
    ]


class ScriptedReportLLM:
    model = "test-report-llama"

    def __init__(self, document_ids: list[int]):
        self.document_ids = document_ids
        self.turn = 0
        self.system_prompt = ""

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        self.system_prompt = messages[0]["content"]
        if not tools:
            return {
                "role": "assistant",
                "content": (
                    "# Project Portfolio Report\n\n## Executive Summary\nThe selected projects were reviewed.\n\n"
                    "## Key Findings\n- The classifier achieved an F1-score of 0.91 (semantic-report.pdf, page 1).\n\n"
                    "## Conclusion\nThe evidence supports the reported result.\n\n## Sources\n- semantic-report.pdf, page 1"
                ),
                "tool_calls": [],
            }
        self.turn += 1
        if self.turn == 1:
            return {"role": "assistant", "content": "", "tool_calls": [{
                "function": {"name": "search_documents", "arguments": {
                    "query": "classification F1-score result", "document_ids": self.document_ids,
                }},
            }]}
        return {
            "role": "assistant",
            "content": (
                "# Project Portfolio Report\n\n## Executive Summary\nThe selected projects were reviewed.\n\n"
                "## Key Findings\n- The classifier achieved an F1-score of 0.91 (semantic-report.pdf, page 1).\n\n"
                "## Conclusion\nThe evidence supports the reported result.\n\n## Sources\n- semantic-report.pdf, page 1"
            ),
            "tool_calls": [],
        }


def test_report_generation_reuses_agent_tools_and_returns_markdown(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    llm = ScriptedReportLLM([document["id"]])
    app.dependency_overrides[get_llm_service] = lambda: llm

    response = client.post("/api/v1/reports/generate", json={
        "document_ids": [document["id"]],
        "instructions": "Create an executive report about the result.",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Project Portfolio Report"
    assert body["content"].startswith("# Project Portfolio Report")
    assert "## Executive Summary" in body["content"]
    assert body["steps"][0]["tool"] == "search_documents"
    assert body["sources"][0]["document_id"] == document["id"]
    assert "standalone Markdown report" in llm.system_prompt


def test_report_generation_validates_request_and_document_state(system):
    client, _, _ = system
    pending = create_document(client, "Pending report")
    assert client.post("/api/v1/reports/generate", json={
        "document_ids": [], "instructions": "Write a report",
    }).status_code == 422
    assert client.post("/api/v1/reports/generate", json={
        "document_ids": [9999], "instructions": "Write a report",
    }).status_code == 404
    assert client.post("/api/v1/reports/generate", json={
        "document_ids": [pending["id"]], "instructions": "Write a report",
    }).status_code == 409


def test_document_agent_validates_documents_before_calling_llm(system):
    client, _, _ = system
    pending = create_document(client, "Pending report")
    llm = ScriptedAgentLLM(pending["id"])
    app.dependency_overrides[get_llm_service] = lambda: llm
    assert client.post("/api/v1/agent/run", json={"document_ids": [], "objective": "Analyse"}).status_code == 422
    assert client.post("/api/v1/agent/run", json={"document_ids": [9999], "objective": "Analyse"}).status_code == 404
    assert client.post("/api/v1/agent/run", json={"document_ids": [pending["id"]], "objective": "Analyse"}).status_code == 409
    assert llm.messages == []


class LoopingAgentLLM:
    model = "test-agent-llama"

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        if not tools:
            return {"role": "assistant", "content": "Stopped after the configured tool limit.", "tool_calls": []}
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "search_documents", "arguments": {"query": "classification F1-score"}}}
        ]}


def test_document_agent_stops_at_tool_call_limit(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    app.dependency_overrides[get_llm_service] = lambda: LoopingAgentLLM()
    settings = app.dependency_overrides[get_settings]()
    settings.agent_max_iterations = 2
    settings.agent_max_tool_calls = 2
    response = client.post("/api/v1/agent/run", json={
        "document_ids": [document["id"]], "objective": "Analyse the report",
    })
    assert response.status_code == 200
    assert response.json()["iterations"] == 2
    assert len(response.json()["steps"]) == 2
    assert "configured tool limit" in response.json()["answer"]


def test_bm25_tokenizer_preserves_exact_identifiers_and_versions():
    tokens = tokenize("Project PRJ-2026/ALPHA uses API v2.4 and code ZXQ-9917.")
    assert "prj-2026/alpha" in tokens
    assert "zxq-9917" in tokens
    assert "v2.4" in tokens
    assert {"prj", "2026", "alpha", "zxq", "9917", "v2", "4"}.issubset(tokens)


def test_agent_tools_expose_real_ids_and_normalize_ordinals():
    definitions = tool_definitions([18, 19])
    allowed = definitions[1]["function"]["parameters"]["properties"]["document_ids"]["items"]["enum"]
    assert allowed == [18, 19]
    assert normalize_document_arguments("search_documents", {"query": "budget", "document_ids": [1, 2]}, [18, 19]) == {
        "query": "budget", "document_ids": [18, 19]
    }
    assert normalize_document_arguments("search_documents", {"query": "budget", "document_ids": "[18, 19]"}, [18, 19]) == {
        "query": "budget", "document_ids": [18, 19]
    }
    assert normalize_document_arguments("get_document_info", {"document_id": 2}, [18, 19]) == {"document_id": 19}
    assert normalize_document_arguments("get_document_content", {"document_id": 1}, [18, 19]) == {"document_id": 18}
    assert normalize_document_arguments("list_documents", {"document_ids": "[18, 19]"}, [18, 19]) == {}
    assert definitions[3]["function"]["name"] == "get_document_content"
    assert definitions[3]["function"]["parameters"]["properties"]["document_id"]["enum"] == [18, 19]


class BroadReportLLM:
    model = "test-broad-report-llama"

    def __init__(self, document_ids: list[int]):
        self.document_ids = document_ids
        self.agent_turn = 0
        self.agent_messages: list[list[dict]] = []
        self.composer_input: dict | None = None

    @staticmethod
    def call(name: str, arguments: dict) -> dict:
        return {"function": {"name": name, "arguments": arguments}}

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        if not tools:
            self.composer_input = json.loads(messages[-1]["content"])
            return {
                "role": "assistant",
                "content": (
                    "# Clubes selecionados\n\n## Resumo Executivo\n\n"
                    "| Clube | País | Fundação |\n|---|---|---|\n"
                    "| Clube A | Portugal | 1901 |\n| Clube B | Espanha | 1902 |\n| Clube C | Alemanha | 1903 |\n\n"
                    "## Principais Conclusões\n\nOs três documentos foram agrupados.\n\n"
                    "## Conclusão\n\nA tabela resume a informação.\n\n## Fontes\n\nOs três documentos selecionados."
                ),
                "tool_calls": [],
            }
        self.agent_turn += 1
        self.agent_messages.append(messages.copy())
        if self.agent_turn == 1:
            return {"role": "assistant", "content": "Posso já criar a tabela.", "tool_calls": []}
        if self.agent_turn == 2:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [self.call("get_document_content", {"document_id": document_id}) for document_id in self.document_ids],
            }
        return {
            "role": "assistant",
            "content": "| Clube | País | Fundação |\n|---|---|---|\n| Clube A | Portugal | 1901 |",
            "tool_calls": [],
        }


def test_broad_report_recovers_from_premature_answer_and_reads_each_document(system):
    client, _, _ = system
    documents = [
        create_document(client, "Clube A | Portugal | Fundação: 1901"),
        create_document(client, "Clube B | Espanha | Fundação: 1902"),
        create_document(client, "Clube C | Alemanha | Fundação: 1903"),
    ]
    for document in documents:
        index(client, document["id"])
    llm = BroadReportLLM([document["id"] for document in documents])
    app.dependency_overrides[get_llm_service] = lambda: llm

    response = client.post("/api/v1/reports/generate", json={
        "document_ids": [document["id"] for document in documents],
        "instructions": "Agrupa a informação destes três documentos numa tabela.",
    })

    assert response.status_code == 200
    body = response.json()
    assert [step["tool"] for step in body["steps"]] == ["get_document_content"] * 3
    assert {source["document_id"] for source in body["sources"]} == {document["id"] for document in documents}
    assert "| Clube | País | Fundação |" in body["content"]
    assert any("choose the most appropriate tools yourself" in message["content"] for message in llm.agent_messages[1])
    assert llm.composer_input is not None
    assert "| Clube | País | Fundação |" in llm.composer_input["agent_draft"]


def test_hybrid_retrieval_recovers_exact_code_below_vector_threshold(system):
    client, _, _ = system
    document = create_document(client, "Classification metadata\nThe exact project identifier is ZXQ-9917.")
    index(client, document["id"])
    llm = ExactCodeLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    settings = app.dependency_overrides[get_settings]()

    hybrid = client.post(
        f'/api/v1/documents/{document["id"]}/ask',
        json={"question": "What does ZXQ-9917 identify?"},
    )
    assert hybrid.status_code == 200
    assert hybrid.json()["answered"] is True
    assert hybrid.json()["sources"][0]["document_id"] == document["id"]
    assert "ZXQ-9917" in llm.prompts[0]

    llm.prompts.clear()
    settings.rag_retrieval_mode = "vector"
    vector_only = client.post(
        f'/api/v1/documents/{document["id"]}/ask',
        json={"question": "What does ZXQ-9917 identify?"},
    )
    assert vector_only.status_code == 200
    assert vector_only.json()["answered"] is False
    assert vector_only.json()["sources"] == []
    assert llm.prompts == []


def test_rrf_deduplicates_chunk_found_by_vector_and_bm25(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    response = client.post(
        f'/api/v1/documents/{document["id"]}/ask',
        json={"question": "What F1-score did the classifier achieve?"},
    )
    assert response.status_code == 200
    assert len(response.json()["sources"]) == 1
    assert response.json()["sources"][0]["score"] == pytest.approx(1.0)


def test_multi_document_rag_uses_only_the_selected_documents(system):
    client, _, _ = system
    first = create_document(client, "Results\nClassifier A achieved an F1-score of 0.91.")
    second = create_document(client, "Results\nClassifier B achieved an F1-score of 0.84.")
    excluded = create_document(client, "Results\nClassifier C achieved an F1-score of 0.12.")
    for document in (first, second, excluded):
        index(client, document["id"])
    llm = CitingAllLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm

    response = client.post(
        "/api/v1/documents/ask",
        json={"document_ids": [second["id"], first["id"]], "question": "Compare the classification results."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert [document["id"] for document in body["documents"]] == [second["id"], first["id"]]
    assert {source["document_id"] for source in body["sources"]} == {first["id"], second["id"]}
    assert all(source["supporting_quote"] in source["text"] for source in body["sources"])
    assert "Classifier A" in llm.prompts[0]
    assert "Classifier B" in llm.prompts[0]
    assert "Classifier C" not in llm.prompts[0]


def test_multi_document_rag_validates_selection(system):
    client, _, _ = system
    indexed = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    pending = create_document(client, "Results\nThe classifier achieved an F1-score of 0.84.")
    index(client, indexed["id"])
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm

    assert client.post("/api/v1/documents/ask", json={"document_ids": [], "question": "Compare results"}).status_code == 422
    assert client.post("/api/v1/documents/ask", json={"document_ids": [indexed["id"], indexed["id"]], "question": "Compare results"}).status_code == 422
    missing = client.post("/api/v1/documents/ask", json={"document_ids": [indexed["id"], 9999], "question": "Compare results"})
    assert missing.status_code == 404
    unavailable = client.post("/api/v1/documents/ask", json={"document_ids": [indexed["id"], pending["id"]], "question": "Compare results"})
    assert unavailable.status_code == 409
    assert llm.prompts == []


def test_rag_uses_only_selected_document_chunks(system):
    client, _, _ = system
    first = create_document(client, "Results\nThe Random Forest classifier achieved an F1-score of 0.91.")
    second = create_document(client, "Results\nThe banana inventory reached twenty-three crates.")
    index(client, first["id"])
    index(client, second["id"])
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm

    response = client.post(f'/api/v1/documents/{first["id"]}/ask', json={"question": "How did the classification model perform?"})
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == first["id"]
    assert body["model"] == "test-llama"
    assert "F1-score of 0.91" in body["answer"]
    assert body["answered"] is True
    assert body["sources"] and all(source["document_id"] == first["id"] for source in body["sources"])
    assert body["sources"][0]["supporting_quote"] in body["sources"][0]["text"]
    assert 0 < body["sources"][0]["score"] <= 1
    assert "F1-score of 0.91" in llm.prompts[0]
    assert "banana inventory" not in llm.prompts[0]
    assert "Use ONLY the excerpts" in llm.prompts[0]


def test_rag_rejects_missing_unindexed_and_invalid_questions(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    url = f'/api/v1/documents/{document["id"]}/ask'
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    assert client.post('/api/v1/documents/9999/ask', json={"question": "What were the results?"}).status_code == 404
    assert client.post(url, json={"question": "What were the results?"}).status_code == 409
    assert client.post(url, json={"question": "  "}).status_code == 422
    assert llm.prompts == []


def test_rag_handles_vector_and_llm_outages(system):
    client, store, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    url = f'/api/v1/documents/{document["id"]}/ask'
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm

    class UnavailableStore:
        def search(self, *args):
            raise VectorStoreError("offline")

    app.dependency_overrides[get_vector_store] = lambda: UnavailableStore()
    assert client.post(url, json={"question": "How did it perform?"}).status_code == 503
    assert llm.prompts == []
    app.dependency_overrides[get_vector_store] = lambda: store
    llm.error = LLMUnavailable("offline")
    assert client.post(url, json={"question": "How did it perform?"}).status_code == 503
    assert client.get('/health').status_code == 200


def test_rag_limits_sent_context(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91. " * 30)
    index(client, document["id"])
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    settings = app.dependency_overrides[get_settings]()
    settings.rag_max_context_chars = 500
    response = client.post(f'/api/v1/documents/{document["id"]}/ask', json={"question": "How did the classification model perform?"})
    assert response.status_code == 200
    assert sum(len(source["text"]) for source in response.json()["sources"]) <= 500


def test_rag_low_score_returns_no_answer_without_ollama(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    response = client.post(f'/api/v1/documents/{document["id"]}/ask', json={"question": "What is the sample size limitation?"})
    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["sources"] == []
    assert "enough information" in response.json()["answer"]
    assert llm.prompts == []


def test_rag_filters_chunks_below_configured_score(system):
    client, _, _ = system
    settings = app.dependency_overrides[get_settings]()
    settings.chunk_size_chars = 100
    settings.chunk_overlap_chars = 0
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.",
                               "Limitations\nThe main limitation is the small sample size.")
    index(client, document["id"])
    llm = CapturingLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    settings.rag_min_score = 0.9
    response = client.post(f'/api/v1/documents/{document["id"]}/ask', json={"question": "How did the classification model perform?"})
    assert response.status_code == 200
    assert len(response.json()["sources"]) == 1
    assert "small sample size" not in llm.prompts[0]


def test_rag_model_must_cite_an_actual_quote(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    llm = CapturingLLM()
    llm.invalid_citation = True
    app.dependency_overrides[get_llm_service] = lambda: llm
    response = client.post(f'/api/v1/documents/{document["id"]}/ask', json={"question": "How did the classification model perform?"})
    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["sources"] == []


def test_rag_model_can_decline_high_score_unsupported_question(system):
    client, _, _ = system
    document = create_document(client, "Results\nThe classifier achieved an F1-score of 0.91.")
    index(client, document["id"])
    llm = CapturingLLM()
    llm.answerable = False
    app.dependency_overrides[get_llm_service] = lambda: llm
    response = client.post(f'/api/v1/documents/{document["id"]}/ask', json={"question": "What budget did the classification project have?"})
    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["sources"] == []
    assert len(llm.prompts) == 1
