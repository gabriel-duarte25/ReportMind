from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.llm.base import LLMService
from app.llm.factory import get_llm_service
from app.rag.service import answer_document_question, answer_documents_question
from app.schemas.rag import (
    DocumentAnswerResponse,
    DocumentQuestionRequest,
    MultiDocumentAnswerResponse,
    MultiDocumentQuestionRequest,
)
from app.services.embeddings import EmbeddingService, get_embedding_service
from app.services.vector_store import VectorStore, get_vector_store

router = APIRouter(prefix="/documents", tags=["rag"])


@router.post("/ask", response_model=MultiDocumentAnswerResponse)
def ask_documents(
    request: MultiDocumentQuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> MultiDocumentAnswerResponse:
    return MultiDocumentAnswerResponse.model_validate(
        answer_documents_question(request.document_ids, request.question, db, settings, embeddings, vectors, llm)
    )


@router.post("/{document_id}/ask", response_model=DocumentAnswerResponse)
def ask_document(
    document_id: int,
    request: DocumentQuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> DocumentAnswerResponse:
    return DocumentAnswerResponse.model_validate(
        answer_document_question(document_id, request.question, db, settings, embeddings, vectors, llm)
    )
