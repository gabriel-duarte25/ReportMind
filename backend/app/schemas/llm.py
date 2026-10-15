from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt must not be empty")
        return prompt


class GenerateResponse(BaseModel):
    response: str
    model: str


class LLMStatusResponse(BaseModel):
    status: Literal["available", "model_missing", "unavailable"]
    provider: str
    model: str
