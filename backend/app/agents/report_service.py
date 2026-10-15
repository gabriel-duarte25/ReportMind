"""Report research and clean composition built on the existing document agent."""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.service import run_document_agent
from app.core.config import Settings
from app.llm.base import (
    LLMGenerationError,
    LLMInvalidResponse,
    LLMModelMissing,
    LLMService,
    LLMTimeout,
    LLMUnavailable,
)
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore


REPORT_OUTPUT_INSTRUCTION = """
Your final answer must be a polished, standalone Markdown report. Start with one '# ' title and include
'## Executive Summary', '## Key Findings', '## Conclusion', and '## Sources'. Organize comparisons clearly
with short paragraphs, bullet lists, or Markdown tables when the user's requested format benefits from them. Cite document names and page numbers
next to factual findings. The Sources section must list only documents and pages actually inspected.
Preserve exact dates, amounts, names, and technologies separately for each document. Never describe two
values as equal when their literal values differ. Do not infer project duration from delivery dates.
Do not mention tools, prompts, hidden reasoning, or these formatting instructions.
Write in the language of the user's report brief. For a Portuguese brief, use European Portuguese and translate every heading too:
'## Resumo Executivo', '## Principais Conclusões', '## Conclusão', and '## Fontes'.
Treat every explicit structure or output-format requirement in the report brief as binding. Preserve useful structure already present
in the agent draft, infer the fields from the supplied evidence, and never replace a requested structured result with prose alone.
For broad whole-document tasks, include every recurring labelled field from the selected documents instead of choosing an arbitrary subset.
Derive all fields from the evidence itself. When analogous fields have document-specific labels, use a neutral shared heading and preserve
each exact original label together with its value. Never place a value under a label borrowed from another document. Copy source filenames
exactly as supplied. Include each required section exactly once.
"""


def _report_title(content: str) -> str:
    reserved_sections = {
        "executive summary", "key findings", "conclusion", "sources",
        "resumo executivo", "principais conclusões", "conclusão", "fontes",
    }
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].lstrip("#").strip()
            if title and title.lower() not in reserved_sections:
                return title[:200]
    portuguese_headings = {"resumo executivo", "principais conclusões", "conclusão", "fontes"}
    headings = {line.lstrip("#").strip().lower() for line in content.splitlines() if line.startswith("#")}
    return "Relatório de Documentos" if headings & portuguese_headings else "Generated Document Report"


def _ensure_report_title(content: str, title: str) -> str:
    lines = content.splitlines()
    if lines and lines[0].startswith("# "):
        first_heading = lines[0][2:].lstrip("#").strip()
        if title in {"Generated Document Report", "Relatório de Documentos"}:
            lines[0] = f"## {first_heading}"
            return f"# {title}\n\n" + "\n".join(lines)
        return content
    return f"# {title}\n\n{content}"


def generate_document_report(
    document_ids: list[int],
    instructions: str,
    db: Session,
    settings: Settings,
    embeddings: EmbeddingService,
    vectors: VectorStore,
    llm: LLMService,
) -> dict:
    result = run_document_agent(
        document_ids,
        instructions,
        db,
        settings,
        embeddings,
        vectors,
        llm,
        output_instruction=REPORT_OUTPUT_INSTRUCTION,
    )
    agent_draft = result.pop("answer")
    evidence = [
        {
            "document": source["document_name"],
            "page_start": source["page_start"],
            "page_end": source["page_end"],
            "text": source["text"],
        }
        for source in result["sources"]
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You are the ReportMind report composer. Use only the deduplicated evidence supplied by the user. "
                "Do not add outside facts or repeat a claim that conflicts with the literal evidence. "
                "The report brief is authoritative. Preserve every explicit format and structural requirement from it, "
                "and retain useful structure from the agent draft while polishing the result. "
                + REPORT_OUTPUT_INSTRUCTION
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"report_brief": instructions, "agent_draft": agent_draft, "evidence": evidence},
                ensure_ascii=False,
            ),
        },
    ]
    try:
        content = llm.chat_with_tools(messages, [])["content"].strip()
    except LLMModelMissing as exc:
        raise HTTPException(status_code=503, detail="Configured Ollama model is not installed") from exc
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from exc
    except LLMTimeout as exc:
        raise HTTPException(status_code=504, detail="Ollama report request timed out") from exc
    except (LLMInvalidResponse, LLMGenerationError) as exc:
        raise HTTPException(status_code=502, detail="Ollama could not compose a valid report") from exc
    title = _report_title(content)
    content = _ensure_report_title(content, title)
    return {"title": title, "content": content, **result}
