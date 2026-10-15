from fastapi import APIRouter

from app.api.v1.system import router as system_router
from app.api.v1.documents import router as documents_router
from app.api.v1.search import router as search_router
from app.api.v1.llm import router as llm_router
from app.api.v1.rag import router as rag_router
from app.api.v1.agent import router as agent_router
from app.api.v1.reports import router as reports_router

router = APIRouter(prefix="/api/v1")
router.include_router(system_router)
router.include_router(documents_router)
router.include_router(search_router)
router.include_router(llm_router)
router.include_router(rag_router)
router.include_router(agent_router)
router.include_router(reports_router)
