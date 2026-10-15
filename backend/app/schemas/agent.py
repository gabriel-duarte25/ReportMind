from typing import Any, Literal

from datetime import datetime

from pydantic import BaseModel, Field, PositiveInt, field_validator


class AgentConversationTurn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)

    @field_validator("question", "answer")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()


class AgentRunRequest(BaseModel):
    document_ids: list[PositiveInt] = Field(min_length=1, max_length=10)
    objective: str = Field(min_length=2, max_length=2000)
    history: list[AgentConversationTurn] = Field(default_factory=list, max_length=6)
    conversation_id: PositiveInt | None = None
    analysis_mode: Literal["standard", "risk_review"] = "standard"

    @field_validator("document_ids")
    @classmethod
    def unique_documents(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Document IDs must be unique")
        return value

    @field_validator("objective")
    @classmethod
    def clean_objective(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Objective must contain at least two non-space characters")
        return value


class AgentStep(BaseModel):
    tool: str
    input: dict[str, Any]
    summary: str


class AgentSource(BaseModel):
    score: float | None = None
    chunk_id: int
    document_id: int
    document_name: str
    text: str
    section: str | None
    page_start: int
    page_end: int


class AgentRunResponse(BaseModel):
    answer: str
    model: str
    iterations: int
    steps: list[AgentStep]
    sources: list[AgentSource]
    conversation_id: int | None = None


class AgentConversationSummary(BaseModel):
    id: int
    title: str
    document_ids: list[int]
    message_count: int
    created_at: datetime
    updated_at: datetime


class AgentConversationMessageResponse(BaseModel):
    id: int
    question: str
    answer: str
    model: str
    iterations: int
    steps: list[AgentStep]
    sources: list[AgentSource]
    created_at: datetime


class AgentConversationDetail(AgentConversationSummary):
    messages: list[AgentConversationMessageResponse]
