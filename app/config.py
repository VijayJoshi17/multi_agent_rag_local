from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    
    # Use path for local disk storage (no docker needed)
    QDRANT_PATH: str = "qdrant_data"
    QDRANT_URL: str | None = None
    
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
