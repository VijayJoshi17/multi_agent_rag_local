"""Single-user API-key authentication.

Enforcement happens in `APIKeyMiddleware`, so it always runs before any route dependency
(DB sessions, uploads, ...). `require_api_key` is kept only to document the scheme in OpenAPI.
"""

import secrets

from fastapi import Request, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(_: str | None = Security(api_key_header)) -> None:
    """No-op at runtime (the middleware enforces); adds the 'Authorize' button to /docs."""
    return None


def _valid(provided: str, expected: str) -> bool:
    return secrets.compare_digest(provided.encode(), expected.encode())


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(  # type: ignore[no-untyped-def]
        self, app, *, api_key: str, protected_prefix: str, public_paths: tuple[str, ...]
    ):
        super().__init__(app)
        self.api_key = api_key
        self.prefix = protected_prefix
        self.public = public_paths

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or not path.startswith(self.prefix)
            or path.startswith(self.public)
        ):
            return await call_next(request)
        provided = request.headers.get("X-API-Key") or request.query_params.get("api_key") or ""
        if not _valid(provided, self.api_key):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {"code": "unauthorized", "message": "Invalid or missing API key"}
                },
                headers={"WWW-Authenticate": "ApiKey"},
            )
        return await call_next(request)
