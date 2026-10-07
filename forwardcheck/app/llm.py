"""Provider-agnostic LLM layer: Gemini / Groq / OpenRouter free tiers with fallback,
retry/backoff, robust JSON parsing and one repair retry."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import re
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings, settings as default_settings

log = logging.getLogger("forwardcheck.llm")
T = TypeVar("T", bound=BaseModel)

MediaPart = tuple[str, bytes]  # (mime, data)


class LLMError(Exception):
    pass


def parse_json(text: str) -> dict:
    """Extract the first JSON object from model output (handles code fences and chatter)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("no valid JSON object found in model output")


class LLM:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or default_settings
        self._or_models: list[dict] | None = None
        self._or_models_at = 0.0
        self._sem = asyncio.Semaphore(3)  # be gentle with free-tier rate limits

    # ---------- availability ----------
    def providers(self) -> list[str]:
        out = []
        if self.s.gemini_key:
            out.append("gemini")
        if self.s.groq_key:
            out.append("groq")
        if self.s.openrouter_key:
            out.append("openrouter")
        return out

    # ---------- HTTP with retry ----------
    async def _post(self, url: str, *, headers: dict, json_body: dict | None = None,
                    data: dict | None = None, files: dict | None = None, timeout: float = 60.0,
                    attempts: int = 3) -> dict:
        last = None
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout) as c:
                    r = await c.post(url, headers=headers, json=json_body, data=data, files=files)
                if r.status_code in (429, 500, 502, 503, 504):
                    wait = min(float(r.headers.get("retry-after", 0) or 0) or (1.5 * 2 ** attempt), 8.0)
                    last = f"HTTP {r.status_code}"
                    await asyncio.sleep(wait + random.random() * 0.5)
                    continue
                if r.status_code >= 400:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                return r.json()
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = type(e).__name__
                await asyncio.sleep(1 + attempt)
        raise LLMError(f"gave up after retries ({last})")

    # ---------- provider calls (return raw text) ----------
    async def _gemini(self, system: str, user: str, media: list[MediaPart], want_json: bool) -> str:
        parts: list[dict] = [{"text": user}]
        for mime, data in media:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
        gen = {"temperature": 0.1}
        if want_json:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
        url = f"{self.s.gemini_base}/models/{self.s.gemini_model}:generateContent"
        j = await self._post(url, headers={"x-goog-api-key": self.s.gemini_key}, json_body=body, timeout=90)
        try:
            cand = j["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in cand if not p.get("thought"))
        except (KeyError, IndexError) as e:
            raise LLMError(f"unexpected Gemini response: {str(j)[:200]}") from e

    async def _openai_style(self, url: str, key: str, model: str, system: str, user: str,
                            media: list[MediaPart], want_json: bool, extra_headers: dict | None = None,
                            attempts: int = 3) -> str:
        if media:
            content: list[dict] = [{"type": "text", "text": user}]
            for mime, data in media:
                b64 = base64.b64encode(data).decode()
                if mime.startswith("image/"):
                    content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
                elif mime.startswith("audio/"):
                    fmt = "mp3" if "mpeg" in mime else "wav"
                    content.append({"type": "input_audio", "input_audio": {"data": b64, "format": fmt}})
        else:
            content = user
        body = {"model": model, "temperature": 0.1,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if want_json:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", **(extra_headers or {})}
        j = await self._post(url, headers=headers, json_body=body, timeout=90, attempts=attempts)
        try:
            return j["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected response: {str(j)[:200]}") from e

    async def _groq(self, system, user, media, want_json):
        if media:
            raise LLMError("groq text model has no media support")
        last = None
        for model in self.s.groq_models:  # model names change; fall through the list on errors
            try:
                return await self._openai_style(f"{self.s.groq_base}/chat/completions", self.s.groq_key,
                                                model, system, user, media, want_json)
            except LLMError as e:
                last = f"{model}: {e}"
                log.info("groq model failed: %s", last)
        raise LLMError(last or "no Groq model configured")

    async def _discover_openrouter(self) -> list[dict]:
        if self._or_models and time.time() - self._or_models_at < 3600:
            return self._or_models
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{self.s.openrouter_base}/models")
            data = r.json()["data"]
        except Exception as e:  # network or schema change: fall back to the generic free router
            log.warning("OpenRouter model discovery failed: %s", e)
            data = []
        free = []
        for m in data:
            p = m.get("pricing", {})
            if str(p.get("prompt")) == "0" and str(p.get("completion")) == "0":
                mid = m["id"]
                if any(b in mid for b in ("safety", "guard", "code", "embed", "lyria")):
                    continue
                free.append({"id": mid, "ctx": m.get("context_length", 0),
                             "modalities": m.get("architecture", {}).get("input_modalities", ["text"])})
        prefer = ("gemma-4-31b", "nemotron-3-super", "gemma-4-26b", "llama", "qwen", "mistral")
        def rank(m):
            for i, k in enumerate(prefer):
                if k in m["id"]:
                    return (i, -m["ctx"])
            return (len(prefer), -m["ctx"])
        free.sort(key=rank)
        free.append({"id": "openrouter/free", "ctx": 0, "modalities": ["text", "image"]})
        self._or_models, self._or_models_at = free, time.time()
        return free

    async def _openrouter_candidates(self, need: str | None) -> list[str]:
        if self.s.openrouter_models and need is None:
            return self.s.openrouter_models
        found = await self._discover_openrouter()
        ids = [m["id"] for m in found if need is None or need in m["modalities"]]
        return (self.s.openrouter_models + [i for i in ids if i not in self.s.openrouter_models])[:4]

    async def _openrouter(self, system, user, media, want_json):
        need = None
        if any(m.startswith("audio/") for m, _ in media):
            need = "audio"
        elif media:
            need = "image"
        last = None
        for model in await self._openrouter_candidates(need):
            if not (model.endswith(":free") or model == "openrouter/free"):
                log.warning("refusing non-free OpenRouter model %s (zero-budget guard)", model)
                continue
            try:
                text = await self._openai_style(
                    f"{self.s.openrouter_base}/chat/completions", self.s.openrouter_key, model, system, user,
                    media, want_json, {"X-Title": "ForwardCheck"}, attempts=1)  # free models 429 often: move on fast
                if text.strip():
                    self.last_model = model
                    return text
                last = f"{model}: empty response"
            except LLMError as e:
                last = f"{model}: {e}"
                log.info("openrouter model failed: %s", last)
        raise LLMError(last or "no OpenRouter model available")

    async def _call(self, provider: str, system, user, media, want_json) -> str:
        fn = {"gemini": self._gemini, "groq": self._groq, "openrouter": self._openrouter}[provider]
        async with self._sem:
            return await fn(system, user, media, want_json)

    # ---------- public API ----------
    async def text(self, system: str, user: str, media: list[MediaPart] | None = None,
                   providers: list[str] | None = None) -> tuple[str, str]:
        """Free-form text (e.g. OCR / transcription). Returns (text, provider)."""
        errors = []
        for p in providers or self.providers():
            if p == "groq" and media:
                continue
            try:
                return (await self._call(p, system, user, media or [], False)).strip(), p
            except LLMError as e:
                errors.append(f"{p}: {e}")
        raise LLMError("; ".join(errors) or "no LLM provider configured (set GEMINI_API_KEY, GROQ_API_KEY or OPENROUTER_API_KEY)")

    async def json(self, system: str, user: str, model: type[T], media: list[MediaPart] | None = None) -> tuple[T, str]:
        """Structured output validated against `model`. Tries each provider; one repair retry each."""
        errors = []
        provs = self.providers()
        if not provs:
            raise LLMError("no LLM provider configured (set GEMINI_API_KEY, GROQ_API_KEY or OPENROUTER_API_KEY)")
        for p in provs:
            if p == "groq" and media:
                continue
            prompt = user
            for attempt in range(2):
                try:
                    raw = await self._call(p, system, prompt, media or [], True)
                    obj = model.model_validate(parse_json(raw))
                    return obj, p
                except (ValueError, ValidationError) as e:
                    errors.append(f"{p}: invalid output ({str(e)[:120]})")
                    prompt = (user + "\n\nYour previous reply was not valid. Problem: " + str(e)[:300] +
                              "\nReturn ONLY one JSON object that matches the requested schema.")
                except LLMError as e:
                    errors.append(f"{p}: {e}")
                    break
        raise LLMError("; ".join(errors[-4:]))
