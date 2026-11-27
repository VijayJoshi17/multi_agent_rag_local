from collections.abc import AsyncIterator

from fastapi import Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.errors import PayloadTooLargeError

limiter = Limiter(key_func=get_remote_address)


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.container.db.sessionmaker() as session:
        yield session


async def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload with a hard size cap (never trusts Content-Length)."""
    buf = bytearray()
    while chunk := await file.read(1024 * 1024):
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise PayloadTooLargeError(
                f"{file.filename} exceeds the {max_bytes // (1024 * 1024)} MB limit"
            )
    return bytes(buf)
