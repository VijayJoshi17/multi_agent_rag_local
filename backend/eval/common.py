"""Shared helpers for the evaluation harness: dataset loading, text matching, pipeline setup."""

import json
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qdrant_client import AsyncQdrantClient

from app.container import Container
from app.core.config import Settings
from app.services.embeddings import SentenceTransformerEmbedder
from app.services.llm import LLMClient
from app.services.vector_store import VectorStore

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
RESULTS_DIR = EVAL_DIR / "results"


@dataclass(slots=True)
class Question:
    id: str
    type: str
    question: str
    reference: str
    must_include: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def answerable(self) -> bool:
        return self.type != "unanswerable"


def normalize(text: str) -> str:
    """Lowercase, unify unicode, drop thousands separators and markdown noise for matching."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"(?<=\d)[,  ](?=\d{3}\b)", "", text)  # 1,200 -> 1200
    text = text.replace("`", "").replace("*", "")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text).strip()


def contains_any(haystack: str, alternatives: str, sep: str = "|") -> bool:
    """True if any non-empty alternative occurs in haystack (after normalisation).

    Answer keywords use "a|b"; evidence passages use "a||b" (they may contain a single "|").
    """
    hay = normalize(haystack)
    alts = [normalize(a) for a in alternatives.split(sep)]
    return any(a and a in hay for a in alts)


def has_evidence(text: str, evidence: str) -> bool:
    return contains_any(text, evidence, sep="||")


def load_questions(path: Path | None = None) -> list[Question]:
    raw = json.loads((path or EVAL_DIR / "questions.json").read_text(encoding="utf-8"))
    questions = [Question(**q) for q in raw]
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in sorted(CORPUS_DIR.glob("*.md")))
    ids = set()
    for q in questions:
        if q.id in ids:
            raise ValueError(f"Duplicate question id {q.id}")
        ids.add(q.id)
        for ev in q.evidence:
            if not has_evidence(corpus, ev):
                raise ValueError(f"{q.id}: evidence not found verbatim in corpus: {ev!r}")
        if q.answerable and not q.evidence:
            raise ValueError(f"{q.id}: answerable question without evidence")
    return questions


def eval_settings(tmp: Path, base: Settings | None = None, **overrides: Any) -> Settings:
    base = base or Settings(_env_file=None)  # type: ignore[call-arg]
    return base.model_copy(update={
        "ENVIRONMENT": "test",
        "DATA_DIR": tmp,
        "DATABASE_URL": f"sqlite+aiosqlite:///{(tmp / 'eval.db').as_posix()}",
        "QDRANT_URL": None,
        **overrides,
    })


class NoLLM:
    """Placeholder for retrieval-only runs: any LLM call is a bug."""

    model = "none"

    async def complete(self, *a: Any, **k: Any) -> str:
        raise RuntimeError("Retrieval evaluation must not call the LLM")

    async def stream(self, *a: Any, **k: Any):  # noqa: ANN201
        raise RuntimeError("Retrieval evaluation must not call the LLM")
        yield ""

    async def ping(self) -> bool:
        return True


async def build_pipeline(settings: Settings, llm: LLMClient | None = None) -> Container:
    """A real container (real embedder, reranker, ingestion) over an in-memory vector store."""
    embedder = SentenceTransformerEmbedder(settings.EMBEDDING_MODEL)
    store = VectorStore(AsyncQdrantClient(location=":memory:"), "eval", embedder.dimension)
    return await Container.build(settings, llm=llm or NoLLM(), embedder=embedder,  # type: ignore[arg-type]
                                 store=store)


async def ingest_corpus(c: Container, questions: list[Question], distractors: bool = True) -> int:
    """Ingest the gold corpus (plus seeded hard negatives) through the production pipeline."""
    files = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(CORPUS_DIR.glob("*.md"))]
    if distractors:
        from eval.distractors import check_no_leaks, generate

        extra = generate()
        check_no_leaks(extra, questions)
        files += extra
    for name, text in files:
        _, skipped = await c.ingestion.register_upload(name, text.encode("utf-8"))
        if skipped:
            raise RuntimeError(f"Corpus file skipped: {skipped}")
    await c.ingestion.wait_idle()
    return await c.store.count()


def temp_dir() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="rag-eval-", ignore_cleanup_errors=True)
