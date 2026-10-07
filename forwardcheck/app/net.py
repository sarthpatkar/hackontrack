"""Safe outbound fetching (SSRF-protected) because users give us arbitrary URLs."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

UA = "Mozilla/5.0 (compatible; ForwardCheck/1.0; +fact-checking research bot)"


class FetchError(Exception):
    pass


def _ip_is_public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


async def assert_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchError("Only http and https links are supported.")
    host = p.hostname
    if not host:
        raise FetchError("Invalid link.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80),
                                                             type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError("Could not resolve that link.") from e
    if not infos or not all(_ip_is_public(i[4][0]) for i in infos):
        raise FetchError("That link points to a private or local address.")


async def safe_get(url: str, *, max_bytes: int = 6_000_000, timeout: float = 10.0,
                   max_redirects: int = 4) -> tuple[str, str, bytes]:
    """GET a URL following redirects manually, re-validating each hop. Returns (final_url, content_type, body)."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                 headers={"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.8,hi;q=0.6"}) as client:
        for _ in range(max_redirects + 1):
            await assert_public_url(url)
            try:
                async with client.stream("GET", url) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            raise FetchError("Bad redirect.")
                        url = urljoin(url, loc)
                        continue
                    if r.status_code >= 400:
                        raise FetchError(f"The site returned an error ({r.status_code}).")
                    chunks, size = [], 0
                    async for chunk in r.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            break
                        chunks.append(chunk)
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    return url, ctype, b"".join(chunks)
            except httpx.HTTPError as e:
                raise FetchError("Could not open that link.") from e
        raise FetchError("Too many redirects.")
