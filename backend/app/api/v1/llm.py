from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.llm.base import (
    LLMGenerationError,
    LLMInvalidResponse,
    LLMModelMissing,
    LLMService,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.factory import get_llm_service
from app.schemas.llm import GenerateRequest, GenerateResponse, LLMStatusResponse

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status", response_model=LLMStatusResponse)
def llm_status(service: Annotated[LLMService, Depends(get_llm_service)]) -> LLMStatusResponse:
    return LLMStatusResponse(status=service.status(), provider=service.provider, model=service.model)


@router.post("/generate", response_model=GenerateResponse)
def llm_generate(
    request: GenerateRequest,
    service: Annotated[LLMService, Depends(get_llm_service)],
) -> GenerateResponse:
    try:
        response = service.generate(request.prompt)
    except LLMModelMissing as exc:
        raise HTTPException(status_code=503, detail="Configured Ollama model is not installed") from exc
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from exc
    except LLMTimeout as exc:
        raise HTTPException(status_code=504, detail="Ollama generation timed out") from exc
    except (LLMInvalidResponse, LLMGenerationError) as exc:
        raise HTTPException(status_code=502, detail="Ollama could not generate a valid response") from exc
    return GenerateResponse(response=response, model=service.model)
