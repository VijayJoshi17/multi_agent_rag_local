from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.schemas.rag import SourceKind

# SQLite drops tzinfo; every timestamp we store is UTC, so re-attach it on the way out.
UTCDateTime = Annotated[
    datetime, AfterValidator(lambda d: d if d.tzinfo else d.replace(tzinfo=UTC))
]

ChatMode = Literal["auto", "documents", "web", "data"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    mode: ChatMode = "auto"
    top_k: int = Field(default=5, ge=1, le=20)
    verify: bool = True
    dataset_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=100)


class SourceOut(BaseModel):
    text: str
    source: str
    kind: SourceKind
    document_id: str | None = None
    page: int | None = None
    url: str | None = None
    score: float | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut] = []
    meta: dict[str, Any] = {}
    feedback: int | None = None
    created_at: UTCDateTime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class FeedbackIn(BaseModel):
    value: Literal[1, -1, 0]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    chunk_count: int
    error: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class UploadResult(BaseModel):
    documents: list[DocumentOut]
    skipped: list[str] = []


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    size_bytes: int
    row_count: int
    columns: list[dict[str, str]]
    created_at: UTCDateTime


class DatasetPreview(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class KnowledgeBaseStats(BaseModel):
    documents: int
    chunks: int


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]
    version: str
    llm_model: str
