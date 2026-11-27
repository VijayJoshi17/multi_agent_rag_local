"""Runs one chat turn: persists messages, executes the agent graph, streams events."""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger, trace_id_var
from app.db.models import Conversation, Message
from app.graph.state import GraphState
from app.schemas.api import ChatRequest, MessageOut, SourceOut
from app.schemas.rag import Chunk

logger = get_logger(__name__)

_DONE = object()


def chunk_to_source(c: Chunk) -> dict[str, Any]:
    return SourceOut(
        text=c.text[:2000], source=c.source, kind=c.kind, document_id=c.document_id,
        page=c.page, url=c.url, score=round(c.score, 4) if c.score is not None else None,
    ).model_dump()


class ChatService:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], graph: Any,
                 history_turns: int):
        self.sessionmaker = sessionmaker
        self.graph = graph
        self.history_messages = history_turns * 2

    async def _prepare(self, req: ChatRequest) -> tuple[str, list[dict[str, str]], str]:
        async with self.sessionmaker() as s:
            if req.conversation_id:
                conv = await s.get(Conversation, req.conversation_id)
                if conv is None:
                    raise NotFoundError("Conversation not found")
            else:
                conv = Conversation(title=req.message.strip()[:60])
                s.add(conv)
                await s.flush()
            rows = (await s.scalars(
                select(Message).where(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc()).limit(self.history_messages)
            )).all()
            history = [{"role": m.role, "content": m.content} for m in reversed(rows)]
            user_msg = Message(conversation_id=conv.id, role="user", content=req.message)
            s.add(user_msg)
            await s.commit()
            return conv.id, history, user_msg.id

    async def stream(self, req: ChatRequest) -> AsyncIterator[dict[str, Any]]:
        trace_id = uuid.uuid4().hex[:16]
        token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        try:
            conversation_id, history, user_message_id = await self._prepare(req)
            yield {"type": "start", "trace_id": trace_id, "conversation_id": conversation_id,
                   "user_message_id": user_message_id}

            queue: asyncio.Queue[Any] = asyncio.Queue()
            timeline: list[dict[str, Any]] = []

            async def emit(event: dict[str, Any]) -> None:
                if event["type"] == "node_end":
                    timeline.append({k: event[k] for k in ("node", "duration_ms", "summary")})
                await queue.put(event)

            initial: GraphState = {
                "question": req.message, "history": history, "mode": req.mode,
                "top_k": req.top_k, "verify": req.verify, "dataset_id": req.dataset_id,
                "attempts": 0,
            }

            async def run_graph() -> GraphState:
                try:
                    return await self.graph.ainvoke(
                        initial, config={"configurable": {"emit": emit}, "recursion_limit": 25}
                    )
                finally:
                    await queue.put(_DONE)

            task = asyncio.create_task(run_graph())
            try:
                while (event := await queue.get()) is not _DONE:
                    yield event
                final: GraphState = await task
            finally:
                if not task.done():  # client disconnected mid-stream
                    task.cancel()

            message = await self._save_answer(conversation_id, final, trace_id, timeline,
                                              int((time.perf_counter() - started) * 1000))
            yield {"type": "final", "message": message.model_dump(mode="json")}
        except AppError as e:
            yield {"type": "error", "code": e.code, "message": e.message, "trace_id": trace_id}
        except Exception:
            logger.exception("Chat turn failed")
            yield {"type": "error", "code": "internal_error",
                   "message": "Something went wrong while answering.", "trace_id": trace_id}
        finally:
            trace_id_var.reset(token)

    async def _save_answer(self, conversation_id: str, final: GraphState, trace_id: str,
                           timeline: list[dict[str, Any]], duration_ms: int) -> MessageOut:
        evidence = [c for c in final.get("evidence") or [] if c.kind != "system"]
        verification = final.get("verification") or {"verdict": "skipped", "reason": ""}
        meta: dict[str, Any] = {
            "trace_id": trace_id,
            "route": final.get("route"),
            "query": final.get("query"),
            "attempts": final.get("attempts", 1),
            "verification": verification,
            "timeline": timeline,
            "duration_ms": duration_ms,
        }
        if analysis := final.get("analysis"):
            meta["analysis"] = analysis
        async with self.sessionmaker() as s:
            msg = Message(
                conversation_id=conversation_id, role="assistant",
                content=final.get("answer") or "", sources=[chunk_to_source(c) for c in evidence],
                meta=meta,
            )
            s.add(msg)
            conv = await s.get(Conversation, conversation_id)
            if conv:
                conv.updated_at = datetime.now(UTC)  # touch for sidebar ordering
            await s.commit()
            return MessageOut.model_validate(msg)
