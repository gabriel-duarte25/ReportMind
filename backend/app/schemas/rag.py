from pydantic import BaseModel, Field, field_validator

from app.schemas.search import SemanticSearchResult


class DocumentQuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Question must contain at least two non-space characters")
        return value


class MultiDocumentQuestionRequest(DocumentQuestionRequest):
    document_ids: list[int] = Field(min_length=1, max_length=10)

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[int]) -> list[int]:
        if any(document_id <= 0 for document_id in value):
            raise ValueError("Document IDs must be positive integers")
        if len(value) != len(set(value)):
            raise ValueError("Document IDs must be unique")
        return value


class RAGSource(SemanticSearchResult):
    supporting_quote: str


class DocumentAnswerResponse(BaseModel):
    document_id: int
    document_name: str
    question: str
    answer: str
    model: str
    answered: bool
    sources: list[RAGSource]


class RAGDocument(BaseModel):
    id: int
    name: str


class MultiDocumentAnswerResponse(BaseModel):
    documents: list[RAGDocument]
    question: str
    answer: str
    model: str
    answered: bool
    sources: list[RAGSource]


class GroundedCitation(BaseModel):
    chunk_id: int
    quote: str


class GroundedAnswer(BaseModel):
    answerable: bool
    answer: str
    citations: list[GroundedCitation]
