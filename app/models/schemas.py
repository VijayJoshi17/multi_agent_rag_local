from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, TypedDict, Annotated
import operator
from datetime import datetime

class ToolFeedback(BaseModel):
    agent_name: str
    success: bool
    feedback: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class DocumentChunk(BaseModel):
    content: str
    metadata: Dict[str, Any]
    score: Optional[float] = None

class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    run_verification: bool = True
    mode: str = "general" # "general" | "data_analyst"
    chat_history: List[Dict[str, str]] = []

class Source(BaseModel):
    text: str
    metadata: Dict[str, Any]

class Answer(BaseModel):
    response: str
    sources: List[Source]
    confidence_score: float
    trace_id: str

# LangGraph State Definition
class AgentGraphState(TypedDict):
    query: str
    chat_history: List[Dict[str, str]]
    route: str | None
    mode: str
    retrieved_docs: List[DocumentChunk]
    summary: str | None
    reasoning_trace: List[str]
    generated_answer: str | None
    verification_status: bool
    verification_feedback: str | None
    retry_count: int
    run_verification: bool
    route: str | None
    logs: Annotated[List[str], operator.add]

class AgentState(BaseModel):
    query: str
    chat_history: List[dict] = []
    retrieved_docs: List[DocumentChunk] = []
    generated_answer: Optional[str] = None
    verification_result: str = "" # ACCURATE | INACCURATE
    mode: str = "general" # general | data_analyst | web_search
    route: Optional[str] = None
    logs: List[str] = [] # Execution logs for monitoring
    summary: Optional[str] = None
    reasoning_trace: List[str] = []
    verification_status: bool = False
    verification_feedback: Optional[str] = None
    run_verification: bool = True
