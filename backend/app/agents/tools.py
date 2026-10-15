"""Document tools exposed to the local agent."""

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, PositiveInt, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.retrieval import retrieve_chunks
from app.services.vector_store import VectorStore


class SearchArguments(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    document_ids: list[PositiveInt] | None = Field(default=None, min_length=1, max_length=10)


class DocumentArguments(BaseModel):
    document_id: PositiveInt


class ChunkArguments(BaseModel):
    chunk_id: PositiveInt


@dataclass
class ToolObservation:
    content: dict[str, Any]
    summary: str
    sources: list[dict]


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List the documents selected for this task and their basic indexing metadata.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search selected PDF chunks with hybrid vector and BM25 retrieval. Use focused queries and call again for separate topics.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Focused search query."},
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional subset of the selected document IDs.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_info",
            "description": "Get filename, page count, chunk count and status for one selected document.",
            "parameters": {
                "type": "object",
                "required": ["document_id"],
                "properties": {"document_id": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_content",
            "description": (
                "Read the indexed text of one selected document in chunk order. Use this for broad tasks that require "
                "understanding, summarising, comparing, grouping, or restructuring the whole content of small documents, "
                "especially when there is no focused search query."
            ),
            "parameters": {
                "type": "object",
                "required": ["document_id"],
                "properties": {"document_id": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chunk",
            "description": "Read one complete chunk by ID when a search result needs closer inspection.",
            "parameters": {
                "type": "object",
                "required": ["chunk_id"],
                "properties": {"chunk_id": {"type": "integer"}},
            },
        },
    },
]


def tool_definitions(selected_document_ids: list[int]) -> list[dict]:
    definitions = deepcopy(TOOL_DEFINITIONS)
    allowed = {"type": "integer", "enum": selected_document_ids}
    definitions[1]["function"]["parameters"]["properties"]["document_ids"]["items"] = allowed
    definitions[2]["function"]["parameters"]["properties"]["document_id"] = allowed
    definitions[3]["function"]["parameters"]["properties"]["document_id"] = allowed
    definitions[1]["function"]["description"] += f" The only allowed document IDs are {selected_document_ids}."
    definitions[2]["function"]["description"] += f" The only allowed document IDs are {selected_document_ids}."
    definitions[3]["function"]["description"] += f" The only allowed document IDs are {selected_document_ids}."
    return definitions


def normalize_document_arguments(name: str, arguments: dict[str, Any], selected_document_ids: list[int]) -> dict[str, Any]:
    """Normalize common argument shapes emitted by small local models."""
    normalized = dict(arguments)

    if name == "list_documents":
        return {}

    def resolve(value: Any) -> Any:
        if isinstance(value, int) and value not in selected_document_ids and 1 <= value <= len(selected_document_ids):
            return selected_document_ids[value - 1]
        return value

    if name == "search_documents":
        values = normalized.get("document_ids")
        if isinstance(values, str):
            try:
                decoded = json.loads(values)
                if isinstance(decoded, list):
                    values = decoded
                    normalized["document_ids"] = decoded
            except json.JSONDecodeError:
                pass
        if isinstance(values, list):
            normalized["document_ids"] = [resolve(value) for value in values]
    elif name in {"get_document_info", "get_document_content"} and "document_id" in normalized:
        normalized["document_id"] = resolve(normalized["document_id"])
    return normalized


def _source(chunk: DocumentChunk, document: Document, score: float | None = None) -> dict:
    return {
        "score": score,
        "chunk_id": chunk.id,
        "document_id": document.id,
        "document_name": document.original_filename,
        "text": chunk.text,
        "section": chunk.section,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
    }


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    selected_document_ids: list[int],
    db: Session,
    settings: Settings,
    embeddings: EmbeddingService,
    vectors: VectorStore,
) -> ToolObservation:
    try:
        if name == "list_documents":
            documents = list(db.scalars(select(Document).where(Document.id.in_(selected_document_ids))))
            by_id = {document.id: document for document in documents}
            items = [
                {
                    "id": by_id[document_id].id,
                    "filename": by_id[document_id].original_filename,
                    "page_count": by_id[document_id].page_count,
                    "chunk_count": by_id[document_id].indexed_chunk_count,
                    "status": by_id[document_id].status,
                    "indexing_status": by_id[document_id].indexing_status,
                }
                for document_id in selected_document_ids
                if document_id in by_id
            ]
            return ToolObservation({"documents": items}, f"Foram listados {len(items)} documentos selecionados.", [])

        if name == "search_documents":
            parsed = SearchArguments.model_validate(arguments)
            target_ids = parsed.document_ids or selected_document_ids
            if not set(target_ids).issubset(selected_document_ids):
                raise ValueError("search_documents can only use the selected documents")
            results = retrieve_chunks(
                parsed.query,
                target_ids,
                settings.agent_search_limit,
                db,
                embeddings,
                vectors,
                settings,
            )
            sources = [
                {
                    "score": result["score"],
                    "chunk_id": result["chunk_id"],
                    "document_id": result["document_id"],
                    "document_name": result["document_name"],
                    "text": result["text"],
                    "section": result["section"],
                    "page_start": result["page_start"],
                    "page_end": result["page_end"],
                }
                for result in results
            ]
            document_count = len({source["document_id"] for source in sources})
            summary = f"Foram encontrados {len(sources)} fragmentos relevantes em {document_count} documentos selecionados."
            return ToolObservation({"query": parsed.query, "results": sources}, summary, sources)

        if name == "get_document_info":
            parsed = DocumentArguments.model_validate(arguments)
            if parsed.document_id not in selected_document_ids:
                raise ValueError("Document is outside the selected set")
            document = db.get(Document, parsed.document_id)
            if document is None:
                raise ValueError("Document not found")
            info = {
                "id": document.id,
                "filename": document.original_filename,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "page_count": document.page_count,
                "chunk_count": document.indexed_chunk_count,
                "status": document.status,
                "indexing_status": document.indexing_status,
                "uploaded_at": document.uploaded_at.isoformat(),
            }
            return ToolObservation(info, f"Metadados carregados para {document.original_filename}.", [])

        if name == "get_document_content":
            parsed = DocumentArguments.model_validate(arguments)
            if parsed.document_id not in selected_document_ids:
                raise ValueError("Document is outside the selected set")
            document = db.get(Document, parsed.document_id)
            if document is None:
                raise ValueError("Document not found")
            chunks = list(db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == parsed.document_id)
                .order_by(DocumentChunk.chunk_index)
            ))
            max_content_chars = 20_000
            used_chars = 0
            sources = []
            content_chunks = []
            truncated = False
            for chunk in chunks:
                remaining = max_content_chars - used_chars
                if remaining <= 0:
                    truncated = True
                    break
                text = chunk.text[:remaining]
                if len(text) < len(chunk.text):
                    truncated = True
                source = _source(chunk, document)
                source["text"] = text
                sources.append(source)
                content_chunks.append({
                    "chunk_id": chunk.id,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section": chunk.section,
                    "text": text,
                })
                used_chars += len(text)
                if truncated:
                    break
            content = {
                "document_id": document.id,
                "filename": document.original_filename,
                "chunks": content_chunks,
                "chunks_returned": len(content_chunks),
                "chunks_total": len(chunks),
                "truncated": truncated,
            }
            summary = f"Conteúdo carregado de {document.original_filename}: {len(content_chunks)} fragmentos."
            return ToolObservation(content, summary, sources)

        if name == "get_chunk":
            parsed = ChunkArguments.model_validate(arguments)
            row = db.execute(
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.id == parsed.chunk_id, DocumentChunk.document_id.in_(selected_document_ids))
            ).one_or_none()
            if row is None:
                raise ValueError("Chunk not found in the selected documents")
            chunk, document = row
            source = _source(chunk, document)
            return ToolObservation(source, f"Fragmento {chunk.id} carregado de {document.original_filename}, página {chunk.page_start}.", [source])

        raise ValueError(f"Unknown tool: {name}")
    except (ValidationError, ValueError) as exc:
        return ToolObservation({"error": str(exc)}, f"A ferramenta falhou: {exc}", [])
