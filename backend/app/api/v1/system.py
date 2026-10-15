import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import engine
from app.schemas.system import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database status check failed")
        return SystemStatusResponse(status="degraded", database="unavailable")
    return SystemStatusResponse(status="operational", database="connected")

