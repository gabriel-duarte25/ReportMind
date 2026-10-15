from typing import Annotated

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.service import run_document_agent
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.llm.base import LLMService
from app.llm.factory import get_llm_service
from app.models.agent_conversation import AgentConversation, AgentConversationMessage
from app.schemas.agent import AgentConversationDetail, AgentConversationSummary, AgentRunRequest, AgentRunResponse
from app.services.embeddings import EmbeddingService, get_embedding_service
from app.services.vector_store import VectorStore, get_vector_store


router = APIRouter(prefix="/agent", tags=["agent"])

RISK_REVIEW_INSTRUCTION = (
    " Perform a comprehensive risk and contradiction review across every selected document. "
    "Inspect the full content of each document before concluding. Separate verified contradictions from potential risks and missing information. "
    "Start with a concise overall assessment. For every finding include: severity (CRITICAL, HIGH, MEDIUM, or LOW), category, evidence, "
    "possible impact, and a practical recommended action. Cite every finding with the exact [chunk:ID] references. "
    "Prioritize material issues involving dates, values, obligations, requirements, scope, ownership, or incompatible statements. "
    "Never invent a risk. If there is insufficient evidence for a category, state that clearly."
)


def _summary(conversation: AgentConversation) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "document_ids": conversation.document_ids,
        "message_count": len(conversation.messages),
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


@router.get("/conversations", response_model=list[AgentConversationSummary])
def list_conversations(db: Annotated[Session, Depends(get_db)]) -> list[AgentConversationSummary]:
    conversations = db.scalars(
        select(AgentConversation)
        .options(selectinload(AgentConversation.messages))
        .order_by(AgentConversation.updated_at.desc())
    ).all()
    return [AgentConversationSummary.model_validate(_summary(conversation)) for conversation in conversations]


@router.get("/conversations/{conversation_id}", response_model=AgentConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> AgentConversationDetail:
    conversation = db.scalar(
        select(AgentConversation)
        .where(AgentConversation.id == conversation_id)
        .options(selectinload(AgentConversation.messages))
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return AgentConversationDetail.model_validate({
        **_summary(conversation),
        "messages": conversation.messages,
    }, from_attributes=True)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    conversation = db.get(AgentConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run", response_model=AgentRunResponse)
def run_agent(
    request: AgentRunRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> AgentRunResponse:
    conversation = None
    history = [turn.model_dump() for turn in request.history]
    if request.conversation_id is not None:
        conversation = db.scalar(
            select(AgentConversation)
            .where(AgentConversation.id == request.conversation_id)
            .options(selectinload(AgentConversation.messages))
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.document_ids != request.document_ids:
            raise HTTPException(status_code=409, detail="Selected documents do not match this conversation")
        history = [
            {"question": message.question, "answer": message.answer}
            for message in conversation.messages[-6:]
        ]

    result = run_document_agent(
        request.document_ids,
        request.objective,
        db,
        settings,
        embeddings,
        vectors,
        llm,
        history=history,
        output_instruction=RISK_REVIEW_INSTRUCTION if request.analysis_mode == "risk_review" else None,
    )
    if conversation is None:
        title = request.objective.strip().replace("\n", " ")[:80]
        conversation = AgentConversation(title=title, document_ids=request.document_ids)
        db.add(conversation)
        db.flush()
    conversation.messages.append(AgentConversationMessage(
        question=request.objective,
        answer=result["answer"],
        model=result["model"],
        iterations=result["iterations"],
        steps=result["steps"],
        sources=result["sources"],
    ))
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    result["conversation_id"] = conversation.id
    return AgentRunResponse.model_validate(result)
