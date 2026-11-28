import asyncio
import re
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from starlette.concurrency import run_in_threadpool

from app.agents.base import Agent, load_prompt, parse_json
from app.core.logging import get_logger
from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.schemas.rag import Chunk
from app.services.embeddings import Reranker
from app.services.fetch import fetch_page
from app.services.llm import LLMClient

logger = get_logger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-^]{1,12}$")


def _ddg_search(query: str, max_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS

    return list(DDGS().text(query, max_results=max_results) or [])


def _quote(ticker: str) -> str | None:
    import yfinance as yf

    fi = yf.Ticker(ticker).fast_info
    price = fi.last_price
    if not price:
        return None
    prev = fi.previous_close or 0
    change = price - prev
    pct = (change / prev * 100) if prev else 0.0
    lines = [
        f"{ticker} last price: {price:,.2f} {fi.currency or ''}".strip(),
        f"Change vs previous close: {change:+,.2f} ({pct:+.2f}%)",
    ]
    if fi.market_cap:
        lines.append(f"Market cap: {fi.market_cap:,.0f}")
    return "\n".join(lines)


class WebSearchAgent(Agent):
    """Plans a search (one LLM call), optionally fetches a live stock quote, searches DDG, then
    reads the top result pages and keeps their most relevant passages."""

    name = "web_search"

    def __init__(self, llm: LLMClient, max_results: int, reranker: Reranker | None = None,
                 pages_to_read: int = 3, passages_per_page: int = 2):
        self.llm = llm
        self.max_results = max_results
        self.reranker = reranker
        self.pages_to_read = pages_to_read
        self.passages_per_page = passages_per_page
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

    async def _plan(self, query: str) -> tuple[str, str | None]:
        raw = await self.llm.complete(f"User question: {query}", system=load_prompt("web_plan"),
                                      json_mode=True, temperature=0)
        plan = parse_json(raw)
        search = str(plan.get("search_query") or query).strip().strip('"') or query
        ticker = plan.get("ticker")
        ticker = str(ticker).upper().strip() if ticker else None
        if ticker in {"NONE", "NULL", ""} or (ticker and not _TICKER_RE.match(ticker)):
            ticker = None
        return search, ticker

    async def _read(self, query: str, hit: dict[str, str]) -> list[Chunk]:
        """Best passages of one result page, or [] if the page can't be read."""
        try:
            page = await asyncio.wait_for(fetch_page(hit["href"]), timeout=12)
        except Exception as e:  # noqa: BLE001 - any failure falls back to the snippet
            logger.info("Could not read %s: %s", hit["href"], e)
            return []
        passages = [p for p in self.splitter.split_text(page.text) if len(p) > 80][:40]
        if not passages:
            return []
        if self.reranker and len(passages) > self.passages_per_page:
            scores = await self.reranker.score(query, passages)
            ranked = sorted(zip(passages, scores, strict=True), key=lambda x: x[1], reverse=True)
            passages = [p for p, _ in ranked]
        title = hit.get("title") or page.title
        return [Chunk(text=p, source=title, kind="web", url=page.url)
                for p in passages[: self.passages_per_page]]

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        search_query, ticker = await self._plan(state["query"])
        await ctx.log(f"Search query: “{search_query}”" + (f" · ticker {ticker}" if ticker else ""))

        # Document passages from an earlier retrieval (docs-then-web fallback) are kept.
        evidence: list[Chunk] = [c for c in state.get("evidence") or [] if c.kind == "document"]
        if ticker:
            try:
                quote = await asyncio.wait_for(run_in_threadpool(_quote, ticker), timeout=10)
                if quote:
                    evidence.append(Chunk(text=quote, source="Yahoo Finance", kind="tool",
                                          url=f"https://finance.yahoo.com/quote/{ticker}"))
                    await ctx.log(f"Fetched live quote for {ticker}.")
            except Exception as e:  # noqa: BLE001
                await ctx.log(f"Quote lookup failed for {ticker}: {e}")

        try:
            results = await asyncio.wait_for(
                run_in_threadpool(_ddg_search, search_query, self.max_results), timeout=15
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Web search failed: %s", e)
            await ctx.log("Web search failed or timed out.")
            results = []

        hits, seen = [], set()
        for r in results:
            if (url := r.get("href") or "") and url not in seen:
                seen.add(url)
                hits.append(r)

        to_read = hits[: self.pages_to_read]
        pages = await asyncio.gather(*(self._read(state["query"], h) for h in to_read))
        read = sum(1 for p in pages if p)
        await ctx.log(f"Read {read} of {len(to_read)} pages in full.")
        for hit, passages in zip(to_read, pages, strict=True):
            evidence += passages or [_snippet(hit)]
        evidence += [_snippet(h) for h in hits[self.pages_to_read:]]
        await ctx.log(f"Collected {len(evidence)} passages.")
        return {"evidence": evidence, "web_fallback": state.get("route") == "retrieve"}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"{len(update.get('evidence', []))} web passages"


def _snippet(hit: dict[str, str]) -> Chunk:
    return Chunk(text=f"{hit.get('title', '')}\n{hit.get('body', '')}".strip(),
                 source=hit.get("title") or hit["href"], kind="web", url=hit["href"])
