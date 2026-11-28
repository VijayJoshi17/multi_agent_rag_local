from typing import Any, Literal, TypedDict

from app.schemas.rag import Chunk

Route = Literal["retrieve", "web_search", "data_analyst"]


class Verification(TypedDict):
    verdict: Literal["supported", "unsupported", "skipped"]
    reason: str


class GraphState(TypedDict, total=False):
    # inputs
    question: str
    history: list[dict[str, str]]
    mode: str
    top_k: int
    verify: bool
    dataset_id: str | None
    document_ids: list[str] | None  # restrict retrieval to these documents
    # working state
    query: str
    route: Route
    evidence: list[Chunk]
    answer: str
    attempts: int
    verification: Verification
    analysis: dict[str, Any]
    web_fallback: bool  # web search already ran after a document retrieval
