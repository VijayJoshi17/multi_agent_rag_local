"""Composition root: builds every long-lived service exactly once at startup."""

from dataclasses import dataclass

from app.agents.contextualizer import ContextualizerAgent
from app.agents.data_analyst import DataAnalystAgent
from app.agents.reasoner import ReasonerAgent
from app.agents.retriever import RetrieverAgent
from app.agents.router import RouterAgent
from app.agents.verifier import VerifierAgent
from app.agents.web_search import WebSearchAgent
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.session import Database
from app.graph.workflow import Agents, build_workflow
from app.services.bm25 import BM25Index
from app.services.chat import ChatService
from app.services.datasets import DatasetService
from app.services.embeddings import (
    CrossEncoderReranker,
    Embedder,
    Reranker,
    SentenceTransformerEmbedder,
)
from app.services.ingestion import IngestionService
from app.services.llm import LLMClient, OpenAICompatibleLLM
from app.services.sandbox import SandboxClient
from app.services.vector_store import VectorStore

logger = get_logger(__name__)


@dataclass
class Container:
    settings: Settings
    db: Database
    llm: LLMClient
    embedder: Embedder
    reranker: Reranker | None
    store: VectorStore
    bm25: BM25Index
    ingestion: IngestionService
    datasets: DatasetService
    sandbox: SandboxClient
    chat: ChatService

    @classmethod
    async def build(
        cls,
        settings: Settings,
        *,
        llm: LLMClient | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        store: VectorStore | None = None,
        sandbox: SandboxClient | None = None,
    ) -> "Container":
        """Overrides let tests inject fakes for the heavy / external pieces."""
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        db = Database(settings.DATABASE_URL)
        await db.create_all()

        llm = llm or OpenAICompatibleLLM(settings)
        embedder = embedder or SentenceTransformerEmbedder(settings.EMBEDDING_MODEL)
        if reranker is None and settings.RERANKER_ENABLED:
            reranker = CrossEncoderReranker(settings.RERANKER_MODEL)
        store = store or VectorStore.create(
            url=settings.QDRANT_URL, path=settings.QDRANT_PATH,
            collection=settings.QDRANT_COLLECTION, dimension=embedder.dimension,
        )
        await store.ensure_collection()
        bm25 = BM25Index()
        await bm25.rebuild(store)

        sandbox = sandbox or SandboxClient(settings.SANDBOX_URL, settings.SANDBOX_TIMEOUT_S)
        datasets = DatasetService(settings, db.sessionmaker)
        ingestion = IngestionService(settings, db.sessionmaker, embedder, store, bm25)

        agents = Agents(
            contextualize=ContextualizerAgent(llm, settings.HISTORY_TURNS),
            router=RouterAgent(llm, embedder, store, bm25, settings),
            retrieve=RetrieverAgent(embedder, store, bm25, reranker, settings),
            web_search=WebSearchAgent(llm, settings.WEB_SEARCH_RESULTS),
            data_analyst=DataAnalystAgent(llm, datasets, sandbox),
            reason=ReasonerAgent(llm),
            verify=VerifierAgent(llm),
        )
        graph = build_workflow(agents, settings.MAX_VERIFY_RETRIES)
        chat = ChatService(db.sessionmaker, graph, settings.HISTORY_TURNS)

        container = cls(settings, db, llm, embedder, reranker, store, bm25, ingestion,
                        datasets, sandbox, chat)
        await ingestion.start()
        logger.info("Container ready (llm=%s, chunks=%d)", settings.LLM_MODEL, bm25.size)
        return container

    async def close(self) -> None:
        await self.ingestion.stop()
        await self.sandbox.close()
        await self.store.close()
        await self.db.dispose()
