from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.search import SemanticSearchRequest, SemanticSearchResponse
from app.services.embeddings import EmbeddingService, get_embedding_service
from app.services.search import semantic_search
from app.services.vector_store import VectorStore, get_vector_store

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/semantic", response_model=SemanticSearchResponse)
def search_semantic(
    request: SemanticSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
) -> SemanticSearchResponse:
    results = semantic_search(request.query, request.limit, request.document_ids, db, embeddings, vectors)
    return SemanticSearchResponse(query=request.query, results=results)
