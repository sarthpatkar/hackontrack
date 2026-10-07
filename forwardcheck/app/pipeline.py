"""Orchestrates ingest -> claims -> evidence -> judge, emitting progress events as it goes."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from . import claims as claims_mod
from . import judge as judge_mod
from . import retrieve, store
from .config import settings
from .i18n import norm_lang
from .ingest import IngestError, ingest
from .lang import detect_indic
from .llm import LLM, LLMError
from .models import CheckResult, Claim, ClaimResult, Evidence, Ingested, Label, Verdict

log = logging.getLogger("forwardcheck.pipeline")
Emit = Callable[[dict], Awaitable[None]]


async def _noop(_: dict) -> None:
    return None


async def check_claim(llm: LLM, claim: Claim, lang: str) -> ClaimResult:
    key = store.cache_key(claim.text_en, lang)
    hit = store.cache_get(key, claim.time_sensitive)
    if hit:
        res = ClaimResult.model_validate(hit)
        res.claim = claim
        res.cached = True
        return res
    evidence = await retrieve.gather(claim, lang)
    verdict, note = await judge_mod.judge(llm, claim, evidence, lang)
    res = ClaimResult(claim=claim, verdict=verdict, evidence=evidence, guardrail_note=note)
    if evidence:  # don't cache 'nothing found': search backends can fail transiently
        store.cache_put(key, res.model_dump(mode="json"))
    return res


async def run_check(llm: LLM, *, text: str | None = None, url: str | None = None,
                    file: tuple[bytes, str, str] | None = None, lang_override: str | None = None,
                    emit: Emit = _noop, ingested: Ingested | None = None) -> CheckResult:
    t0 = time.time()
    await emit({"event": "stage", "stage": "ingest", "msg": "Reading your content…"})
    ing = ingested or await ingest(llm, text=text, url=url, file=file)
    await emit({"event": "stage", "stage": "claims", "msg": "Finding the claims to check…",
                "input_type": ing.input_type, "preview": ing.text[:300]})
    cl, total = await claims_mod.extract(llm, ing.text)
    lang = norm_lang(lang_override or detect_indic(ing.text) or cl.language)
    note = ing.note
    out = CheckResult(input_type=ing.input_type, language=lang, source_url=ing.source_url, source_date=ing.source_date,
                      extracted_text_preview=ing.text[:500], note=note)
    if not cl.claims:
        out.note = cl.no_claims_reason or "No checkable claim found."
        out.elapsed_ms = int((time.time() - t0) * 1000)
        await emit({"event": "claims", "claims": [], "language": lang})
        return out
    if total > len(cl.claims):
        out.note = ((note + " ") if note else "") + f"Found {total} claims; checking the {len(cl.claims)} most important."
    await emit({"event": "claims", "claims": [c.model_dump() for c in cl.claims], "language": lang})
    await emit({"event": "stage", "stage": "evidence", "msg": "Searching reliable sources and judging…"})

    sem = asyncio.Semaphore(settings.max_parallel_claims)
    results: dict[str, ClaimResult] = {}

    async def work(c: Claim) -> None:
        async with sem:
            try:
                res = await check_claim(llm, c, lang)
            except LLMError as e:
                log.warning("claim %s failed: %s", c.id, e)
                from .i18n import t
                res = ClaimResult(claim=c, evidence=[], guardrail_note=f"error: {e}",
                                  verdict=Verdict(label=Label.CANNOT_BE_CONFIRMED, what_is_wrong=t("error", lang),
                                                  summary=t("error", lang)))
            results[c.id] = res
            await emit({"event": "result", "result": res.model_dump(mode="json")})

    await asyncio.gather(*[work(c) for c in cl.claims])
    out.results = [results[c.id] for c in cl.claims]
    out.elapsed_ms = int((time.time() - t0) * 1000)
    store.log_check(out.input_type, lang, [r.verdict.label.value for r in out.results], out.elapsed_ms)
    return out
