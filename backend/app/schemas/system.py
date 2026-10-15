from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["reportmind-backend"] = "reportmind-backend"


class SystemStatusResponse(BaseModel):
    status: Literal["operational", "degraded"]
    service: Literal["reportmind-backend"] = "reportmind-backend"
    database: Literal["connected", "unavailable"]

