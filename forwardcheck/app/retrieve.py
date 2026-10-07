"""Stage 3: gather evidence for a claim from reliable sources only."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from math import sqrt

import httpx

from datetime import date as _date

from .config import ALLOWLIST, CATEGORY_DOMAINS, FACT_CHECK_DOMAINS, settings, source_info
from .ingest import extract_html, pdf_to_text
from .models import Claim, Evidence
from .net import safe_get

log = logging.getLogger("forwardcheck.retrieve")

_STOP = set("the a an of to in on for and or is are was were be been it this that with as at by from will has have "
            "not no you your we they he she his her their its all any can may more most new says said".split())
_search_sem = asyncio.Semaphore(3)
_search_cache: dict[str, tuple[float, list[dict]]] = {}


def tokens(s: str) -> list[str]:
    return [w for w in re.findall(r"[\wऀ-ॿ]+", s.lower()) if w not in _STOP and (len(w) > 2 or w.isdigit())]


def best_passage(text: str, claim: str, max_chars: int = 380) -> tuple[str, float]:
    """Pick the sentence(s) of `text` that overlap most with the claim. Returns (passage, relevance 0-1)."""
    q = set(tokens(claim))
    if not q or not text:
        return "", 0.0
    sents = [s.strip() for s in re.split(r"(?<=[.!?।])\s+|\n+", text) if len(s.strip()) > 25]
    if not sents:
        return text[:max_chars], 0.0
    best_i, best = 0, -1.0
    for i, s in enumerate(sents):
        st = set(tokens(s))
        score = len(q & st) / sqrt(len(q) * max(len(st), 1))
        if score > best:
            best_i, best = i, score
    passage = sents[best_i]
    if len(passage) < 160 and best_i + 1 < len(sents):  # add the next sentence for context
        passage += " " + sents[best_i + 1]
    return passage[:max_chars].strip(), max(best, 0.0)


# ---------- search backends ----------
async def _ddg(query: str) -> list[dict]:
    now = time.time()
    hit = _search_cache.get(query)
    if hit and now - hit[0] < 1800:
        return hit[1]

    def run() -> list[dict]:
        from ddgs import DDGS
        return list(DDGS().text(query, region="in-en", max_results=8))

    async with _search_sem:
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(run), timeout=15)
        except Exception as e:
            log.info("ddg search failed for %r: %s", query, e)
            return []
    out = [{"url": r.get("href", ""), "title": r.get("title", ""), "snippet": r.get("body", "")} for r in raw]
    _search_cache[query] = (now, out)
    return out


async def _tavily(query: str) -> list[dict]:
    domains = list(ALLOWLIST)[:60]
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://api.tavily.com/search",
                             headers={"Authorization": f"Bearer {settings.tavily_key}"},
                             json={"query": query, "max_results": 8, "include_domains": domains,
                                   "search_depth": "basic"})
        r.raise_for_status()
        return [{"url": x["url"], "title": x.get("title", ""), "snippet": x.get("content", "")}
                for x in r.json().get("results", [])]
    except Exception as e:
        log.info("tavily failed: %s", e)
        return []


async def _factcheck_api(query: str, lang: str) -> list[Evidence]:
    if not settings.factcheck_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://factchecktools.googleapis.com/v1alpha1/claims:search",
                            params={"query": query[:250], "pageSize": 6, "languageCode": lang},
                            headers={"x-goog-api-key": settings.factcheck_key})
        r.raise_for_status()
        claims = r.json().get("claims", [])
    except Exception as e:
        log.info("fact check API failed: %s", e)
        return []
    out = []
    for c in claims:
        for rev in c.get("claimReview", [])[:1]:
            pub = rev.get("publisher", {})
            snippet = f'{pub.get("name", "A fact-checker")} rated "{c.get("text", "")[:160]}" as: {rev.get("textualRating", "?")}'
            if rev.get("title"):
                snippet += f" — {rev['title']}"
            out.append(Evidence(id="", source_name=pub.get("name", "Fact-checker"), domain=pub.get("site", ""),
                                url=rev.get("url", ""), published_at=(rev.get("reviewDate") or "")[:10] or None,
                                snippet=snippet[:380], kind="fact_check_db", rating=rev.get("textualRating")))
    return [e for e in out if e.url]


def _site_group(domains: list[str]) -> str:
    return "(" + " OR ".join(f"site:{d}" for d in domains) + ")"


FC_GROUP = _site_group(FACT_CHECK_DOMAINS)


async def _web_candidates(claim: Claim) -> list[dict]:
    """Search fact-checkers and the most relevant official sources. Grouped site: queries run in parallel
    (a keyless search takes ~6 s per query, so we keep the number small)."""
    qs = claim.search_queries or [claim.text_en]
    q0 = qs[0]
    cat = CATEGORY_DOMAINS.get(claim.category, CATEGORY_DOMAINS["other"])
    queries = [f"{q0} fake fact check {FC_GROUP}", f"{q0} {_site_group(cat)}"]
    if len(qs) > 1:  # a differently-phrased (or native-language) query finds checks the first one misses
        queries.append(f"{qs[1]} fact check {FC_GROUP}")

    async def run(qs_: list[str]) -> list[dict]:
        if settings.tavily_key:
            return [r for b in await asyncio.gather(*[_tavily(q) for q in qs_[:2]]) for r in b]
        return [r for b in await asyncio.gather(*[_ddg(q) for q in qs_]) for r in b]

    results = await run(queries)
    if not results:  # every backend failed or was rate-limited: wait briefly and retry once
        await asyncio.sleep(2)
        results = await run(queries)
    if len({r["url"] for r in results if source_info(r["url"])}) < 2:  # thin: widen with plain queries
        results += await run([f"{q0} fact check", q0])
    seen, out = set(), []
    for r in results:
        u = r["url"]
        info = source_info(u) if u else None
        if info and u not in seen:
            seen.add(u)
            out.append(r)
    fc = set(FACT_CHECK_DOMAINS)
    # fact-checkers first (they address the claim itself), PDFs last (slow, noisy)
    out.sort(key=lambda r: (source_info(r["url"])[1] not in fc, r["url"].lower().endswith(".pdf")))
    return out


async def _page_evidence(cand: dict, claim: Claim, sem: asyncio.Semaphore) -> Evidence | None:
    name, domain = source_info(cand["url"])  # type: ignore[misc]
    text, date, title = "", None, None
    async with sem:
        try:
            final, ctype, body = await safe_get(cand["url"], timeout=7, max_bytes=2_000_000)
            if "pdf" in ctype:
                text, _ = await pdf_to_text(body)
            else:
                text, date, title = extract_html(body, final)
        except Exception as e:  # a failed page is not fatal: fall back to the search snippet
            log.info("page fetch failed %s: %s", cand["url"], e)
    passage, rel = best_passage(text, claim.text_en) if text else ("", 0.0)
    if not passage:
        passage, rel = best_passage(cand.get("snippet", ""), claim.text_en)
        passage = passage or cand.get("snippet", "")[:300]
    if not passage:
        return None
    title = (title or cand.get("title") or "").strip()
    if title and title.lower() not in passage.lower():  # fact-check headlines carry the verdict ("... is fake")
        passage = f"[{title[:140]}] {passage}"[:480]
    if date and date[:10] >= _date.today().isoformat():  # page-render dates are not publication dates
        date = None
    if not date:
        m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", cand.get("snippet", ""))
        date = m.group(1) if m else None
    return Evidence(id="", source_name=name, domain=domain, url=cand["url"],
                    published_at=date[:10] if date else None, snippet=passage, kind="web", relevance=round(rel, 3))


async def gather(claim: Claim, lang: str = "en") -> list[Evidence]:
    fc, cands = await asyncio.gather(_factcheck_api(claim.text_en, "hi" if lang == "hi" else "en"),
                                     _web_candidates(claim))
    sem = asyncio.Semaphore(4)
    pages = await asyncio.gather(*[_page_evidence(c, claim, sem) for c in cands[:6]])
    web = [p for p in pages if p]
    web.sort(key=lambda e: -e.relevance)
    if len(web) > 2:  # drop passages that share nothing with the claim when better ones exist
        web = [e for e in web if e.relevance > 0.05] or web[:2]
    out = (fc + web)[: settings.max_evidence]
    for i, e in enumerate(out, 1):
        e.id = f"e{i}"
    return out
