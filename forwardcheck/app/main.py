"""FastAPI app: web UI + JSON/streaming API + Twilio WhatsApp webhook."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import shutil
import time
from collections import defaultdict, deque
from html import escape
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from . import store
from .config import ROOT, settings
from .i18n import norm_lang, t
from .ingest import IngestError, ingest
from .llm import LLM, LLMError
from .media import tesseract_available
from .pipeline import run_check
from .reply import format_messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("forwardcheck")

app = FastAPI(title="ForwardCheck", version="1.0")
llm = LLM()
WEB = ROOT / "web"

# ---------------- rate limiting (per client IP, in memory) ----------------
_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(request: Request) -> bool:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        return True
    q.append(now)
    return False


def friendly_error(e: Exception) -> tuple[int, str]:
    if isinstance(e, IngestError):
        return 422, str(e)
    if isinstance(e, LLMError):
        log.warning("LLM failure: %s", e)
        return 503, "The AI service is busy or not configured right now. Please try again in a minute."
    log.exception("unexpected error")
    return 500, "Something went wrong while checking this."


async def read_upload(file: UploadFile | None) -> tuple[bytes, str, str] | None:
    if file is None or not file.filename:
        return None
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise IngestError("That file is too large (limit 16 MB).")
    return data, file.filename, file.content_type or ""


# ---------------- web + API ----------------
@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "llm_providers": llm.providers(),
        "ocr_tesseract": tesseract_available(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "speech_to_text": bool(settings.gemini_key or settings.groq_key or settings.openrouter_key),
        "search": "tavily" if settings.tavily_key else "duckduckgo (keyless)",
        "google_factcheck_api": bool(settings.factcheck_key),
        "whatsapp_configured": bool(settings.twilio_sid and settings.twilio_token),
    }


@app.get("/api/stats")
async def stats():
    return await asyncio.to_thread(store.stats)


@app.post("/api/check")
async def api_check(request: Request, text: str = Form(""), url: str = Form(""), language: str = Form(""),
                    file: UploadFile | None = File(None)):
    if rate_limited(request):
        return JSONResponse({"error": "Too many requests. Please wait a minute."}, status_code=429)
    try:
        res = await run_check(llm, text=text or None, url=url or None, file=await read_upload(file),
                              lang_override=language or None)
        return res.model_dump(mode="json")
    except Exception as e:
        code, msg = friendly_error(e)
        return JSONResponse({"error": msg}, status_code=code)


@app.post("/api/check/stream")
async def api_check_stream(request: Request, text: str = Form(""), url: str = Form(""), language: str = Form(""),
                           file: UploadFile | None = File(None)):
    """Newline-delimited JSON events so the UI can render each claim as soon as it is judged."""
    if rate_limited(request):
        return JSONResponse({"error": "Too many requests. Please wait a minute."}, status_code=429)
    try:
        upload = await read_upload(file)
    except IngestError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    q: asyncio.Queue = asyncio.Queue()

    async def emit(ev: dict) -> None:
        await q.put(ev)

    async def runner():
        try:
            res = await run_check(llm, text=text or None, url=url or None, file=upload,
                                  lang_override=language or None, emit=emit)
            await q.put({"event": "done", "summary": res.model_dump(mode="json", exclude={"results"})})
        except Exception as e:
            _, msg = friendly_error(e)
            await q.put({"event": "error", "message": msg})
        finally:
            await q.put(None)

    task = asyncio.create_task(runner())

    async def gen():
        try:
            while True:
                ev = await q.get()
                if ev is None:
                    break
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        finally:
            task.cancel()

    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})


# ---------------- WhatsApp (Twilio) ----------------
def twilio_signature_ok(request_url: str, params: dict[str, str], signature: str) -> bool:
    if not settings.twilio_token:
        return False
    data = request_url + "".join(k + params[k] for k in sorted(params))
    mac = hmac.new(settings.twilio_token.encode(), data.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), signature or "")


def twiml(text: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>'
    return Response(xml, media_type="application/xml")


LANG_WORDS = {"hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi", "marathi": "mr", "मराठी": "mr", "english": "en"}
HELP_WORDS = {"hi", "hello", "hey", "help", "start", "menu", "namaste", "नमस्ते", "नमस्कार"}


async def send_whatsapp(to: str, body: str) -> None:
    if not (settings.twilio_sid and settings.twilio_token):
        log.warning("Twilio credentials missing; cannot send WhatsApp reply")
        return
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json",
                         auth=(settings.twilio_sid, settings.twilio_token),
                         data={"From": settings.twilio_from, "To": to, "Body": body})
    if r.status_code >= 300:
        log.warning("Twilio send failed %s: %s", r.status_code, r.text[:200])


async def download_twilio_media(url: str) -> bytes:
    host = (httpx.URL(url).host or "").lower()
    if not (host == "api.twilio.com" or host.endswith(".twilio.com") or host.endswith(".twiliocdn.com")):
        raise IngestError("Unexpected media source.")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url, auth=(settings.twilio_sid, settings.twilio_token))
    if r.status_code >= 400:
        raise IngestError("I couldn't download that attachment.")
    if len(r.content) > settings.max_upload_bytes:
        raise IngestError("That file is too large.")
    return r.content


async def process_whatsapp(user: str, body: str, media_url: str | None, media_type: str, pref: str | None) -> None:
    lang = pref or "en"
    try:
        file = None
        if media_url:
            data = await download_twilio_media(media_url)
            file = (data, "attachment", media_type)
        ing = await ingest(llm, text=body or None, file=file)
        if file and body:  # a caption goes along with the attachment
            ing.text = f"{body}\n\n{ing.text}"
        res = await run_check(llm, lang_override=pref, ingested=ing)
        for m in format_messages(res):
            await send_whatsapp(user, m)
            await asyncio.sleep(0.6)  # keep message order
    except IngestError as e:
        await send_whatsapp(user, str(e))
    except Exception as e:
        log.warning("whatsapp processing failed: %s", e)
        await send_whatsapp(user, t("error", lang))


@app.post("/whatsapp")
async def whatsapp(request: Request, background: BackgroundTasks):
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if settings.validate_twilio:
        base = settings.public_base_url or str(request.base_url).rstrip("/")
        if not twilio_signature_ok(base + request.url.path, params, request.headers.get("x-twilio-signature", "")):
            return Response("invalid signature", status_code=403)
    user, body = params.get("From", ""), params.get("Body", "").strip()
    n_media = int(params.get("NumMedia", "0") or 0)
    pref = store.get_lang(user)
    lang = pref or "en"
    low = body.lower()
    if n_media == 0 and low in LANG_WORDS:
        store.set_lang(user, LANG_WORDS[low])
        return twiml(t("lang_set", LANG_WORDS[low]))
    if n_media == 0 and (low in HELP_WORDS or not body):
        return twiml(t("help", lang))
    background.add_task(process_whatsapp, user, body, params.get("MediaUrl0") if n_media else None,
                        params.get("MediaContentType0", ""), pref)
    return twiml(t("checking", lang))
