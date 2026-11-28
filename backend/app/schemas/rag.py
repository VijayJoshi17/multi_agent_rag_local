from typing import Any, Literal

from pydantic import BaseModel

SourceKind = Literal["document", "web", "tool", "analysis", "system"]


class Chunk(BaseModel):
    """A unit of evidence passed between agents (document chunk, web hit, tool output)."""

    text: str
    source: str
    kind: SourceKind = "document"
    document_id: str | None = None
    chunk_index: int = 0
    page: int | None = None
    url: str | None = None
    score: float | None = None
    extra: dict[str, Any] = {}

    @property
    def key(self) -> str:
        if self.document_id is not None:
            return f"{self.document_id}:{self.chunk_index}"
        return f"{self.source}:{hash(self.text)}"

    def payload(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "page": self.page,
            "url": self.url,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any], score: float | None = None) -> "Chunk":
        return cls(
            text=payload.get("text", ""),
            source=payload.get("source", "unknown"),
            document_id=payload.get("document_id"),
            chunk_index=payload.get("chunk_index", 0),
            page=payload.get("page"),
            url=payload.get("url"),
            score=score,
        )
