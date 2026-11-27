import asyncio
import re
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.agents.base import Agent, load_prompt, parse_json
from app.core.logging import get_logger
from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.schemas.rag import Chunk
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
    """Plans a search (one LLM call), optionally fetches a live stock quote, then searches DDG."""

    name = "web_search"

    def __init__(self, llm: LLMClient, max_results: int):
        self.llm = llm
        self.max_results = max_results

    async def _plan(self, query: str) -> tuple[str, str | None]:
        raw = await self.llm.complete(f"User question: {query}", system=load_prompt("web_plan"),
                                      json_mode=True, max_tokens=120, temperature=0)
        plan = parse_json(raw)
        search = str(plan.get("search_query") or query).strip().strip('"') or query
        ticker = plan.get("ticker")
        ticker = str(ticker).upper().strip() if ticker else None
        if ticker in {"NONE", "NULL", ""} or (ticker and not _TICKER_RE.match(ticker)):
            ticker = None
        return search, ticker

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        search_query, ticker = await self._plan(state["query"])
        await ctx.log(f"Search query: “{search_query}”" + (f" · ticker {ticker}" if ticker else ""))

        evidence: list[Chunk] = []
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

        seen: set[str] = set()
        for r in results:
            url = r.get("href") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            evidence.append(Chunk(
                text=f"{r.get('title', '')}\n{r.get('body', '')}".strip(),
                source=r.get("title") or url, kind="web", url=url,
            ))
        await ctx.log(f"Collected {len(evidence)} web results.")
        return {"evidence": evidence}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"{len(update.get('evidence', []))} web results"
