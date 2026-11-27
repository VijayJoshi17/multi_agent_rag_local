from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.core.errors import NotFoundError
from app.db.models import Conversation, Message
from app.schemas.api import (
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    FeedbackIn,
    MessageOut,
)

router = APIRouter(tags=["conversations"])


async def _get(s: AsyncSession, conversation_id: str) -> Conversation:
    conv = await s.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("Conversation not found")
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = 50, s: AsyncSession = Depends(get_session)
) -> list[Conversation]:
    rows = await s.scalars(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(min(limit, 200))
    )
    return list(rows)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, s: AsyncSession = Depends(get_session)):
    conv = await s.scalar(
        select(Conversation).where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if conv is None:
        raise NotFoundError("Conversation not found")
    return conv


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: str, body: ConversationUpdate, s: AsyncSession = Depends(get_session)
) -> Conversation:
    conv = await _get(s, conversation_id)
    conv.title = body.title
    await s.commit()
    return conv


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, s: AsyncSession = Depends(get_session)):
    await s.delete(await _get(s, conversation_id))
    await s.commit()
    return Response(status_code=204)


@router.post("/messages/{message_id}/feedback", response_model=MessageOut)
async def message_feedback(
    message_id: str, body: FeedbackIn, s: AsyncSession = Depends(get_session)
) -> Message:
    msg = await s.get(Message, message_id)
    if msg is None or msg.role != "assistant":
        raise NotFoundError("Message not found")
    msg.feedback = body.value or None
    await s.commit()
    return msg
