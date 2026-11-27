from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.deps import limiter
from app.api.routes import chat, conversations, datasets, documents, health
from app.container import Container
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.security import APIKeyMiddleware, require_api_key

logger = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    container_factory: Callable[[Settings], Awaitable[Container]] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_runtime()
    configure_logging(settings.LOG_LEVEL, settings.LOG_JSON)
    factory = container_factory or Container.build

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = await factory(settings)
        try:
            yield
        finally:
            await app.state.container.close()

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version=health.VERSION,
        description="Multi-agent Retrieval-Augmented Generation: hybrid search, web search, "
                    "sandboxed data analysis and answer verification, orchestrated with LangGraph.",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "prod" else None,
        redoc_url=None,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    register_exception_handlers(app)

    # NB: Starlette runs the last-added middleware first. Order (outer → inner):
    # CORS → security headers → API key, so even 401s carry CORS headers.
    if settings.auth_enabled:
        app.add_middleware(
            APIKeyMiddleware,
            api_key=settings.API_KEY.get_secret_value(),
            protected_prefix=settings.API_PREFIX,
            public_paths=(f"{settings.API_PREFIX}/health",),
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    protected = [Depends(require_api_key)]
    app.include_router(health.router, prefix=settings.API_PREFIX)
    for r in (chat.router, conversations.router, documents.router, datasets.router):
        app.include_router(r, prefix=settings.API_PREFIX, dependencies=protected)

    Instrumentator(excluded_handlers=["/metrics", f"{settings.API_PREFIX}/health/.*"]).instrument(
        app
    ).expose(app, include_in_schema=False)

    return app
