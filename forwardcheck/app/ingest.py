"""Turn any supported input (text, image, audio, PDF, URL) into clean text."""
from __future__ import annotations

import asyncio
import json
import logging
import re

import pymupdf as fitz  # PyMuPDF
import trafilatura

from .config import settings
from .media import ocr_image, tesseract_available, transcribe
from .llm import LLM, LLMError
from .models import Ingested
from .net import FetchError, safe_get

log = logging.getLogger("forwardcheck.ingest")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic")
AUDIO_EXT = (".ogg", ".opus", ".mp3", ".wav", ".m4a", ".aac", ".webm", ".flac", ".amr", ".mp4")


class IngestError(Exception):
    """Message is safe to show to end users."""


def kind_of(filename: str, mime: str) -> str:
    mime = (mime or "").lower()
    name = (filename or "").lower()
    if mime == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if mime.startswith("image/") or name.endswith(IMAGE_EXT):
        return "image"
    if mime.startswith("audio/") or mime == "video/webm" or name.endswith(AUDIO_EXT):
        return "audio"
    if mime.startswith("text/") or name.endswith(".txt"):
        return "text"
    raise IngestError("Unsupported file type. Send text, an image, a voice note, a PDF or a link.")


def _clip(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[: settings.max_text_chars]


def extract_html(html: str | bytes, url: str | None = None) -> tuple[str, str | None, str | None]:
    """Returns (text, date, title) from an HTML page."""
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    raw = trafilatura.extract(html, url=url, output_format="json", with_metadata=True,
                              include_comments=False, favor_recall=True)
    if not raw:
        return "", None, None
    d = json.loads(raw)
    return d.get("text", "") or "", d.get("date"), d.get("title")


def _pdf_text_sync(data: bytes, ocr: bool) -> tuple[str, int, int]:
    doc = fitz.open(stream=data, filetype="pdf")
    pages, total = [], doc.page_count
    for i, page in enumerate(doc):
        if i >= settings.max_pdf_pages:
            break
        t = page.get_text().strip()
        if len(t) < 20 and ocr:  # scanned page
            try:
                import pytesseract
                from PIL import Image
                import io
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                t = pytesseract.image_to_string(img, lang="eng+hin+mar").strip()
            except Exception:
                t = ""
        pages.append(t)
    return "\n\n".join(pages), total, len(pages)


async def pdf_to_text(data: bytes) -> tuple[str, str | None]:
    try:
        text, total, read = await asyncio.to_thread(_pdf_text_sync, data, tesseract_available())
    except Exception as e:
        raise IngestError("I couldn't open that PDF.") from e
    note = f"Read {read} of {total} pages." if total > read else None
    return text, note


async def url_to_text(url: str) -> Ingested:
    try:
        final, ctype, body = await safe_get(url)
    except FetchError as e:
        raise IngestError(str(e)) from e
    if "pdf" in ctype or final.lower().endswith(".pdf"):
        text, note = await pdf_to_text(body)
        return Ingested(text=_clip(text), input_type="url", source_url=final, note=note)
    text, date, title = extract_html(body, final)
    if len(text) < 80:
        raise IngestError("I couldn't read the article text on that page (it may need a login or block bots).")
    if title:
        text = f"{title}\n\n{text}"
    return Ingested(text=_clip(text), input_type="url", source_url=final, source_date=date)


async def ingest(llm: LLM, *, text: str | None = None, url: str | None = None,
                 file: tuple[bytes, str, str] | None = None) -> Ingested:
    """file = (bytes, filename, mime)."""
    if file is not None:
        data, filename, mime = file
        kind = kind_of(filename, mime)
        if kind == "pdf":
            body, note = await pdf_to_text(data)
            if not body.strip():
                raise IngestError("That PDF has no readable text.")
            return Ingested(text=_clip(body), input_type="pdf", note=note)
        if kind == "image":
            body, method = await ocr_image(data, mime, llm)
            if not body.strip():
                raise IngestError("I couldn't find any text in that image.")
            return Ingested(text=_clip(body), input_type="image", note=f"OCR: {method}")
        if kind == "audio":
            try:
                body, method = await transcribe(data, mime, filename, llm)
            except LLMError as e:
                log.warning("transcription failed: %s", e)
                raise IngestError("I couldn't transcribe that voice note right now. Please try again, or send the text.") from e
            if not body.strip():
                raise IngestError("I couldn't hear any speech in that voice note.")
            return Ingested(text=_clip(body), input_type="audio", note=f"Speech-to-text: {method}")
        return Ingested(text=_clip(data.decode("utf-8", errors="replace")), input_type="text")

    if url:
        return await url_to_text(url.strip())

    text = (text or "").strip()
    if not text:
        raise IngestError("Please send a message, screenshot, voice note, PDF or link.")
    m = URL_RE.search(text)
    if m and len(URL_RE.sub("", text).strip()) < 40:  # message is basically just a link
        return await url_to_text(m.group(0))
    return Ingested(text=_clip(text), input_type="text")
