from pydantic import BaseModel, Field, PositiveInt, field_validator


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    document_ids: list[PositiveInt] | None = Field(default=None, max_length=100)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Query must contain at least two non-space characters")
        return value

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Document IDs must be unique")
        return value


class SemanticSearchResult(BaseModel):
    score: float
    chunk_id: int
    document_id: int
    document_name: str
    text: str
    section: str | None
    page_start: int
    page_end: int


class SemanticSearchResponse(BaseModel):
    query: str
    results: list[SemanticSearchResult]
