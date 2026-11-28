"""Fetch a public web page and extract its readable text, safely.

Both web-search page reading and "add a URL to the knowledge base" fetch URLs the server did not
choose, so this guards against SSRF: only http(s), every redirect hop re-validated, and hostnames
that resolve to private, loopback, link-local or otherwise non-public addresses are refused
(that blocks e.g. http://sandbox:8001, http://localhost, cloud metadata at 169.254.169.254).
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 4
TIMEOUT_S = 10.0
USER_AGENT = "Mozilla/5.0 (compatible; AgenticRAG/1.0; +https://github.com)"


class FetchError(AppError):
    status_code = 422
    code = "fetch_failed"


@dataclass(slots=True)
class Page:
    url: str
    title: str
    text: str


async def _check_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http(s) URLs are supported")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, None,
                                                             type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError(f"Could not resolve {parts.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError("That address is not a public website")
    # shortcut: the IP is checked here but httpx resolves again (DNS-rebinding window); pin the
    # resolved IP in the transport if this ever fetches from untrusted users at scale.


async def _download(url: str) -> tuple[str, str, str]:
    """Return (final_url, content_type, body) after validated redirects."""
    async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False,
                                 headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _check_public(url)
            async with client.stream("GET", url) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"The page returned HTTP {resp.status_code}")
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in ("text/html", "application/xhtml+xml", "text/plain"):
                    raise FetchError(f"Unsupported content type '{ctype or 'unknown'}'")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise FetchError("The page is too large")
                return str(resp.url), ctype, body.decode(resp.encoding or "utf-8", "replace")
    raise FetchError("Too many redirects")


def _extract(html: str, url: str) -> tuple[str, str]:
    import trafilatura

    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True) or ""
    meta = trafilatura.extract_metadata(html)
    return (meta.title if meta and meta.title else ""), text


async def fetch_page(url: str) -> Page:
    try:
        final_url, ctype, body = await _download(url.strip())
    except httpx.HTTPError as e:
        raise FetchError(f"Could not fetch the page ({type(e).__name__})") from e
    if ctype == "text/plain":
        title, text = "", body
    else:
        title, text = await run_in_threadpool(_extract, body, final_url)
    if not text.strip():
        raise FetchError("No readable text found on the page")
    return Page(url=final_url, title=title.strip() or urlsplit(final_url).netloc, text=text)
