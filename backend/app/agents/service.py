"""Small, explicit tool-calling loop for document analysis."""

import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.tools import execute_tool, normalize_document_arguments, tool_definitions
from app.core.config import Settings
from app.llm.base import (
    LLMGenerationError,
    LLMInvalidResponse,
    LLMModelMissing,
    LLMService,
    LLMTimeout,
    LLMUnavailable,
)
from app.models.document import Document
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore


logger = logging.getLogger(__name__)


def _validate_documents(document_ids: list[int], db: Session, embeddings: EmbeddingService) -> list[Document]:
    documents = list(db.scalars(select(Document).where(Document.id.in_(document_ids))))
    by_id = {document.id: document for document in documents}
    missing = [document_id for document_id in document_ids if document_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Documents not found: {', '.join(map(str, missing))}")
    unavailable = [
        document.original_filename
        for document in documents
        if document.status != "ready"
        or document.indexing_status != "indexed"
        or document.embedding_model != embeddings.model_name
    ]
    if unavailable:
        raise HTTPException(
            status_code=409,
            detail="Process and index every selected document before running the agent: " + ", ".join(unavailable),
        )
    return [by_id[document_id] for document_id in document_ids]


def _llm_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMModelMissing):
        return HTTPException(status_code=503, detail="Configured Ollama model is not installed")
    if isinstance(exc, LLMUnavailable):
        return HTTPException(status_code=503, detail="Ollama is unavailable")
    if isinstance(exc, LLMTimeout):
        return HTTPException(status_code=504, detail="Ollama agent request timed out")
    return HTTPException(status_code=502, detail="Ollama could not produce a valid agent response")


def _arguments(call: dict[str, Any]) -> dict[str, Any]:
    raw = call["function"].get("arguments", {})
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must be an object")
    return parsed


def run_document_agent(
    document_ids: list[int],
    objective: str,
    db: Session,
    settings: Settings,
    embeddings: EmbeddingService,
    vectors: VectorStore,
    llm: LLMService,
    output_instruction: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict:
    documents = _validate_documents(document_ids, db, embeddings)
    selected = ", ".join(f"{document.id}: {document.original_filename}" for document in documents)
    tools = tool_definitions(document_ids)
    output_format = f" {output_instruction.strip()}" if output_instruction else ""
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are the ReportMind Document Agent. Complete the user's objective using only the selected PDFs and the provided tools. "
                "You have no document knowledge until you call a tool, so you MUST call at least one tool before answering. "
                "Previous user and assistant messages may be provided for conversational context. Use them to resolve follow-up references, "
                "but treat them as unverified context: retrieve the relevant document evidence again for the current answer. "
                "Choose tools according to the objective. Use focused search_documents calls for specific facts or topics. "
                "For broad objectives that require understanding, grouping, comparing, or restructuring the full content of small documents, "
                "use get_document_content for the relevant selected documents. "
                "Keep documents distinct, never fill gaps with outside knowledge, and explicitly say when evidence is missing. "
                "When a tool result explicitly contains a requested value, treat that value as available and do not claim it is missing. "
                "Your final answer must always use the same language as the user's objective; when that language is Portuguese, use European Portuguese. "
                "Cite every factual claim taken from a document with the exact chunk identifier returned by the tool, using the format [chunk:123]. "
                "Place each citation immediately after the claim it supports. You may cite more than one chunk when needed. "
                "Never invent a chunk identifier and do not use uncited document evidence. "
                "Also mention document names and pages naturally when they help the answer. "
                "Do not describe hidden reasoning; return only the useful final analysis after the tool work is complete. "
                f"Selected documents and their exact database IDs: {selected}. Use these exact IDs, not ordinal numbers such as 1 or 2."
                f"{output_format}"
            ),
        },
    ]
    for turn in history or []:
        messages.extend([
            {"role": "user", "content": turn["question"]},
            {"role": "assistant", "content": turn["answer"]},
        ])
    messages.append({"role": "user", "content": objective})
    steps: list[dict] = []
    sources_by_id: dict[int, dict] = {}
    tool_call_count = 0
    iterations = 0
    answer = ""
    db.rollback()

    try:
        for iteration in range(1, settings.agent_max_iterations + 1):
            iterations = iteration
            assistant = llm.chat_with_tools(messages, tools)
            messages.append(assistant)
            calls = assistant.get("tool_calls", [])
            logger.info(
                "document_agent_iteration iteration=%s tool_calls=%s has_content=%s",
                iteration,
                [call.get("function", {}).get("name") for call in calls],
                bool(assistant.get("content", "").strip()),
            )
            if not calls:
                if sources_by_id:
                    answer = assistant["content"].strip()
                    break
                messages.append({
                    "role": "user",
                    "content": (
                        "You tried to finish before inspecting any document content. Continue the task and choose the most appropriate tools yourself. "
                        "For a focused question, use search_documents with a meaningful query. For a broad summary, comparison, grouping, or "
                        "restructuring task, inspect each relevant small document with get_document_content. You may also use list_documents, "
                        "get_document_info, or get_chunk as needed. Do not produce the final answer until content chunks have been inspected. "
                        f"The exact selected document IDs are {document_ids}."
                    ),
                })
                continue

            for call in calls:
                if tool_call_count >= settings.agent_max_tool_calls:
                    break
                name = call["function"]["name"]
                try:
                    arguments = _arguments(call)
                    arguments = normalize_document_arguments(name, arguments, document_ids)
                except (ValueError, json.JSONDecodeError) as exc:
                    arguments = {}
                    observation = {"error": f"Invalid tool arguments: {exc}"}
                    summary = observation["error"]
                    observed_sources: list[dict] = []
                else:
                    result = execute_tool(
                        name,
                        arguments,
                        document_ids,
                        db,
                        settings,
                        embeddings,
                        vectors,
                    )
                    observation = result.content
                    summary = result.summary
                    observed_sources = result.sources
                    db.rollback()

                tool_call_count += 1
                steps.append({"tool": name, "input": arguments, "summary": summary})
                logger.info(
                    "document_agent_tool tool=%s arguments=%s sources=%s summary=%s",
                    name,
                    arguments,
                    len(observed_sources),
                    summary,
                )
                for source in observed_sources:
                    existing = sources_by_id.get(source["chunk_id"])
                    if existing is None or (source.get("score") or 0) > (existing.get("score") or 0):
                        sources_by_id[source["chunk_id"]] = source
                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(observation, ensure_ascii=False, default=str),
                })

            if tool_call_count >= settings.agent_max_tool_calls:
                break

        if not sources_by_id:
            logger.warning("document_agent_no_evidence steps=%s", steps)
            raise HTTPException(status_code=502, detail="Agent could not retrieve evidence from the selected documents")
        if not answer:
            messages.append({
                "role": "user",
                "content": (
                    "Tool execution is complete. Produce the final grounded answer now without calling another tool. "
                    "Review every successful search observation and use all requested facts that are explicitly present; "
                    "do not report a value as missing when it appears in an observed chunk. "
                    "Cite every factual claim with the exact source chunk identifier in the format [chunk:123]."
                ),
            })
            final_message = llm.chat_with_tools(messages, [])
            answer = final_message["content"].strip()
    except (LLMModelMissing, LLMUnavailable, LLMTimeout, LLMInvalidResponse, LLMGenerationError) as exc:
        raise _llm_error(exc) from exc

    if not answer:
        raise HTTPException(status_code=502, detail="Agent did not produce a final answer")
    return {
        "answer": answer,
        "model": llm.model,
        "iterations": iterations,
        "steps": steps,
        "sources": list(sources_by_id.values()),
    }
