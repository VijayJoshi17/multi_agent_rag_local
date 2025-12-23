from app.agents.base import BaseAgent
from app.models.schemas import AgentState, DocumentChunk
from app.utils.logger import setup_logger
from duckduckgo_search import DDGS
import yfinance as yf
import re
import asyncio
from typing import List, Optional

logger = setup_logger(__name__)


class WebSearchAgent(BaseAgent):
    """
    WebSearchAgent
    ----------------
    Improvements over previous version:
    - Clear separation of concerns (stock detection, query generation, search execution)
    - Safer ticker validation + richer yfinance fallback handling
    - Better DDG result scoring & deduplication
    - Timeouts around network-heavy operations
    - Consistent metadata for downstream agents
    """

    STOCK_TICKER_REGEX = re.compile(r"^[A-Z0-9.]{1,10}$")

    def __init__(self):
        super().__init__(name="WebSearch")

    # =============================================================
    # PUBLIC ENTRYPOINT
    # =============================================================
    async def run(self, state: AgentState) -> AgentState:
        # 1) Try numeric stock query resolution
        stock_docs = await self._handle_stock_query(state.query)
        if stock_docs:
            state.retrieved_docs = stock_docs
            return state

        # 2) Generate optimized web search query
        search_query = await self._generate_search_query(state.query)
        logger.info(f"Web search query: '{search_query}'")

        # 3) Execute web search with fallback
        web_docs = await self._execute_web_search(search_query)
        state.retrieved_docs = web_docs
        return state

    # =============================================================
    # 1. STOCK QUERY HANDLING
    # =============================================================
    async def _handle_stock_query(self, query: str) -> Optional[List[DocumentChunk]]:
        ticker_symbol = await self._detect_stock_ticker(query)

        if not ticker_symbol:
            return None

        logger.info(f"Detected numeric stock query for: {ticker_symbol}")

        try:
            ticker = yf.Ticker(ticker_symbol)
            fi = ticker.fast_info

            if not fi or not fi.last_price:
                raise ValueError("Missing fast_info price data")

            current_price = fi.last_price
            previous_close = fi.previous_close or 0
            currency = fi.currency or ""

            change = current_price - previous_close
            pct_change = (
                (change / previous_close) * 100 if previous_close else 0
            )

            content = (
                f"Stock Symbol: {ticker_symbol}\n"
                f"Current Price: {current_price:.2f} {currency}\n"
                f"Change: {change:.2f} ({pct_change:.2f}%)\n"
                f"Source: Yahoo Finance (yfinance)"
            )

            return [
                DocumentChunk(
                    content=content,
                    metadata={
                        "source": "yfinance",
                        "type": "tool",
                        "confidence": "high",
                    },
                )
            ]

        except Exception as e:
            logger.warning(f"yfinance failed for {ticker_symbol}: {e}")
            return None

    async def _detect_stock_ticker(self, query: str) -> Optional[str]:
        system_prompt = """
You are a financial query classifier and ticker extractor.

TASK:
- Decide if the question REQUIRES numeric stock market data
  (price, market cap, PE, returns, performance).

RULES:
- Output ONLY the official stock ticker symbol (uppercase) if numeric data is required.
- Otherwise output NONE.
- No explanations.
- One token only.

EXAMPLES:
Q: What is Tesla stock price today?
A: TSLA

Q: Market cap of Reliance Industries?
A: RELIANCE.NS

Q: News about Apple CEO
A: NONE

Q: Should I invest in Nvidia?
A: NONE
"""

        prompt = f"User Query: {query}\nAnswer:"
        response = await self.call_llm(prompt, system_prompt=system_prompt)

        ticker = response.strip().replace('"', '').upper()

        if ticker == "NONE":
            return None

        if self.STOCK_TICKER_REGEX.match(ticker):
            return ticker

        logger.debug(f"Rejected invalid ticker output: {ticker}")
        return None

    # =============================================================
    # 2. SEARCH QUERY GENERATION
    # =============================================================
    async def _generate_search_query(self, query: str) -> str:
        system_prompt = """
You are a professional web search query optimizer.

GOAL:
Transform the user's question into a concise, unambiguous,
high-recall search query.

RULES:
- Preserve entities (people, orgs, places, years).
- Fix obvious spelling mistakes.
- Prefer specific phrasing over generic words.
- Output ONLY the optimized query.

EXAMPLES:
User: who is the father of nation of india
Output: Father of the Nation of India

User: shubmal gill ipl team
Output: Shubman Gill IPL team

User: capital of russia
Output: Capital city of Russia
"""

        prompt = f"User Question: {query}\nSearch Query:"
        response = await self.call_llm(prompt, system_prompt=system_prompt)

        return response.strip().replace('"', '')

    # =============================================================
    # 3. WEB SEARCH EXECUTION
    # =============================================================
    async def _execute_web_search(self, search_query: str) -> List[DocumentChunk]:
        docs = []

        # Attempt 1: DuckDuckGo
        try:
            logger.info("Attempting DuckDuckGo search")
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: list(
                        DDGS().text(
                            search_query,
                            region="us-en",
                            max_results=6,
                            backend="html",
                        )
                    )
                ),
                timeout=6,
            )

            for r in self._filter_ddg_results(results):
                content = (
                    f"Title: {r.get('title')}\n"
                    f"Snippet: {r.get('body')}\n"
                    f"URL: {r.get('href')}"
                )
                docs.append(
                    DocumentChunk(
                        content=content,
                        metadata={
                            "source": r.get('href'),
                            "type": "web",
                            "confidence": "medium",
                        },
                    )
                )

            if docs:
                logger.info(f"DDG returned {len(docs)} usable results")
                return docs

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")

        # Attempt 2: Google + Trafilatura fallback
        return await self._google_fallback(search_query)

    # =============================================================
    # FALLBACK SEARCH
    # =============================================================
    async def _google_fallback(self, search_query: str) -> List[DocumentChunk]:
        docs = []
        logger.info("Engaging Google + Trafilatura fallback")

        try:
            from googlesearch import search
            import trafilatura

            urls = list(search(search_query, num_results=3, lang="en"))

            for url in urls:
                try:
                    downloaded = trafilatura.fetch_url(url)
                    if not downloaded:
                        continue

                    text = trafilatura.extract(downloaded)
                    if not text:
                        continue

                    snippet = text[:900].replace("\n", " ")
                    content = (
                        f"Title: {url}\n"
                        f"Snippet: {snippet}...\n"
                        f"URL: {url}"
                    )

                    docs.append(
                        DocumentChunk(
                            content=content,
                            metadata={
                                "source": url,
                                "type": "web_scraped",
                                "confidence": "low",
                            },
                        )
                    )

                except Exception as scrape_err:
                    logger.debug(f"Scrape failed for {url}: {scrape_err}")

            logger.info(f"Fallback produced {len(docs)} documents")

        except Exception as e:
            logger.error(f"Google fallback failed: {e}")

        return docs

    # =============================================================
    # HELPERS
    # =============================================================
    def _filter_ddg_results(self, results: List[dict]) -> List[dict]:
        """Remove spam, duplicates, and non-English-heavy results."""
        seen_urls = set()
        clean_results = []

        for r in results:
            url = r.get("href")
            if not url or url in seen_urls:
                continue

            text_blob = f"{r.get('title', '')} {r.get('body', '')}"
            if not self._is_mostly_english(text_blob):
                continue

            seen_urls.add(url)
            clean_results.append(r)

        return clean_results

    def _is_mostly_english(self, text: str) -> bool:
        if not text:
            return False
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        return (ascii_chars / len(text)) > 0.6
