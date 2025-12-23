from fastapi import FastAPI
from app.utils.logger import setup_logger
from app.api import chat, upload

logger = setup_logger(__name__)

app = FastAPI(
    title="Multi-Agent RAG System (Free Version)",
    description="A production-grade RAG system using Ollama and local embeddings.",
    version="0.1.0"
)

app.include_router(chat.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")

@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "Multi-Agent RAG System (Ollama-based) is running"}
