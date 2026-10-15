from pydantic import BaseModel, Field, PositiveInt, field_validator

from app.schemas.agent import AgentSource, AgentStep


class ReportGenerateRequest(BaseModel):
    document_ids: list[PositiveInt] = Field(min_length=1, max_length=10)
    instructions: str = Field(min_length=2, max_length=2000)

    @field_validator("document_ids")
    @classmethod
    def unique_documents(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Document IDs must be unique")
        return value

    @field_validator("instructions")
    @classmethod
    def clean_instructions(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Instructions must contain at least two non-space characters")
        return value


class ReportGenerateResponse(BaseModel):
    title: str
    content: str
    model: str
    iterations: int
    steps: list[AgentStep]
    sources: list[AgentSource]


class ReportExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("title", "content")
    @classmethod
    def clean_export_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Report text cannot be empty")
        return value
