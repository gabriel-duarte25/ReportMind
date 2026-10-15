import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas.system import HealthResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
app = FastAPI(title="ReportMind API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse()


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
