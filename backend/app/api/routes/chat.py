import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_container, limiter
from app.container import Container
from app.core.config import get_settings
from app.schemas.api import ChatRequest

router = APIRouter(tags=["chat"])


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "/chat/stream",
    summary="Ask a question; streams agent events as Server-Sent Events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
@limiter.limit(lambda: get_settings().RATE_LIMIT_CHAT)
async def chat_stream(
    request: Request, body: ChatRequest, c: Container = Depends(get_container)
) -> StreamingResponse:
    """Event types: `start`, `node_start`, `node_end`, `log`, `code`, `token`,
    `answer_reset`, `final`, `error`."""

    async def events() -> AsyncIterator[str]:
        async for event in c.chat.stream(body):
            if await request.is_disconnected():
                break
            yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
