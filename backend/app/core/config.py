from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---------------------------------------------------------------
    APP_NAME: str = "Agentic RAG"
    ENVIRONMENT: Literal["dev", "prod", "test"] = "dev"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Single-user auth. Empty -> auth disabled (only allowed outside prod).
    API_KEY: SecretStr = SecretStr("")

    # --- LLM (any OpenAI-compatible endpoint: OpenRouter, Ollama /v1, ...) ---
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "nvidia/nemotron-3.5-super-vl:free"
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_S: float = 90.0
    LLM_MAX_RETRIES: int = 2

    # --- Retrieval ---------------------------------------------------------
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_ENABLED: bool = True
    QDRANT_URL: str | None = None
    QDRANT_PATH: str = "storage/qdrant"
    QDRANT_COLLECTION: str = "documents"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    CANDIDATE_POOL: int = 30
    # Head of the fused list sent to the cross-encoder. 10 matched 20/40 on the retrieval eval
    # (backend/eval) at half the latency; see eval/results/retrieval-latest.md.
    RERANK_CANDIDATES: int = 10
    DEFAULT_TOP_K: int = 5
    ROUTER_SEMANTIC_HIGH: float = 0.45
    ROUTER_SEMANTIC_LOW: float = 0.30
    ROUTER_BM25_HIGH: float = 4.0

    # --- Agents ------------------------------------------------------------
    MAX_VERIFY_RETRIES: int = 1
    HISTORY_TURNS: int = 6
    WEB_SEARCH_RESULTS: int = 6

    # --- Storage -----------------------------------------------------------
    DATA_DIR: Path = Path("storage")
    DATABASE_URL: str = "sqlite+aiosqlite:///storage/app.db"
    MAX_UPLOAD_MB: int = 25
    MAX_ZIP_MEMBERS: int = 200
    MAX_ZIP_UNCOMPRESSED_MB: int = 200

    # --- Sandbox -----------------------------------------------------------
    SANDBOX_URL: str = "http://localhost:8001"
    SANDBOX_TIMEOUT_S: float = 30.0

    # --- Rate limiting -----------------------------------------------------
    RATE_LIMIT_CHAT: str = "20/minute"
    RATE_LIMIT_UPLOAD: str = "30/minute"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def documents_dir(self) -> Path:
        return self.DATA_DIR / "documents"

    @property
    def datasets_dir(self) -> Path:
        return self.DATA_DIR / "datasets"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.API_KEY.get_secret_value())

    def validate_for_runtime(self) -> None:
        if self.ENVIRONMENT == "prod" and not self.auth_enabled:
            raise RuntimeError("API_KEY must be set when ENVIRONMENT=prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()
