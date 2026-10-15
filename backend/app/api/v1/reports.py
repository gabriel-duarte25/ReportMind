from typing import Annotated

import re
import unicodedata

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.agents.report_service import generate_document_report
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.llm.base import LLMService
from app.llm.factory import get_llm_service
from app.schemas.report import ReportExportRequest, ReportGenerateRequest, ReportGenerateResponse
from app.services.embeddings import EmbeddingService, get_embedding_service
from app.services.vector_store import VectorStore, get_vector_store
from app.services.report_pdf import render_report_pdf


router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate", response_model=ReportGenerateResponse)
def generate_report(
    request: ReportGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embeddings: Annotated[EmbeddingService, Depends(get_embedding_service)],
    vectors: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> ReportGenerateResponse:
    return ReportGenerateResponse.model_validate(
        generate_document_report(
            request.document_ids,
            request.instructions,
            db,
            settings,
            embeddings,
            vectors,
            llm,
        )
    )


@router.post("/export/pdf")
def export_report_pdf(request: ReportExportRequest) -> Response:
    ascii_title = unicodedata.normalize("NFKD", request.title).encode("ascii", "ignore").decode().lower()
    filename = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-") or "reportmind-report"
    return Response(
        content=render_report_pdf(request.title, request.content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )
