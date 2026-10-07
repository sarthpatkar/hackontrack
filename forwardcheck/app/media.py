"""Turn images and audio into text: Tesseract + vision LLM for OCR, Gemini/Groq Whisper for speech."""
from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from .config import settings
from .llm import LLM, LLMError

log = logging.getLogger("forwardcheck.media")

OCR_PROMPT = (
    "Transcribe ALL text visible in this image exactly as written, in its original language and script "
    "(English, Hindi, Marathi etc.). Keep the reading order. If the image is a chat screenshot, include the "
    "message text but not UI chrome (battery, time). Do not summarise, translate or add commentary. "
    "If there is no text, reply with exactly: NO_TEXT"
)
TRANSCRIBE_PROMPT = (
    "Transcribe this voice message exactly as spoken, in its original language and script "
    "(English, Hindi or Marathi; use Devanagari for Hindi/Marathi). Do not translate, summarise or add commentary. "
    "If there is no speech, reply with exactly: NO_SPEECH"
)
GEMINI_AUDIO_OK = {"audio/wav", "audio/mp3", "audio/mpeg", "audio/aiff", "audio/aac", "audio/ogg", "audio/flac"}


def tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _ocr_tesseract_sync(data: bytes) -> tuple[str, float]:
    import pytesseract

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) < 1400:  # small screenshots OCR poorly; upscale
        scale = 1400 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    img = ImageOps.autocontrast(img)
    cfg = "--psm 6"
    d = pytesseract.image_to_data(img, lang="eng+hin+mar", config=cfg, output_type=pytesseract.Output.DICT)
    words, confs = [], []
    for w, c in zip(d["text"], d["conf"]):
        try:
            c = float(c)
        except ValueError:
            continue
        if w.strip() and c >= 0:
            words.append(w)
            confs.append(c)
    text = pytesseract.image_to_string(img, lang="eng+hin+mar", config=cfg).strip()
    return text, (sum(confs) / len(confs) if confs else 0.0)


async def ocr_image(data: bytes, mime: str, llm: LLM) -> tuple[str, str]:
    """Returns (text, method). Tesseract first (local, unlimited); vision LLM when OCR is weak."""
    text, conf, method = "", 0.0, "none"
    if tesseract_available():
        try:
            text, conf = await asyncio.to_thread(_ocr_tesseract_sync, data)
            method = "tesseract"
        except Exception as e:
            log.warning("tesseract failed: %s", e)
    devanagari = bool(re.search(r"[\u0900-\u097F]", text))  # Tesseract is weakest on Indic scripts
    good = len(text) >= 40 and conf >= 70 and not devanagari
    if not good and llm.providers():
        try:
            vis, prov = await asyncio.wait_for(
                llm.text("You are an OCR engine.", OCR_PROMPT,
                         media=[(mime if mime.startswith("image/") else "image/jpeg", data)]), timeout=25)
            if vis and vis.strip() != "NO_TEXT" and len(vis) > len(text) * 0.7:
                return vis.strip(), f"vision:{prov}"
        except (LLMError, asyncio.TimeoutError) as e:
            log.info("vision OCR failed or timed out (using Tesseract result): %s", e)
    return ("" if text.strip() == "NO_TEXT" else text), method


async def _ffmpeg_to_wav(data: bytes) -> bytes:
    if not shutil.which("ffmpeg"):
        raise LLMError("ffmpeg is not installed (needed to convert this audio format)")
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in"), Path(d, "out.wav")
        src.write_bytes(data)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0 or not dst.exists():
            raise LLMError("could not decode that audio file: " + err.decode()[:150])
        return dst.read_bytes()


async def _groq_whisper(data: bytes, filename: str, mime: str) -> str:
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post("https://api.groq.com/openai/v1/audio/transcriptions",
                         headers={"Authorization": f"Bearer {settings.groq_key}"},
                         data={"model": "whisper-large-v3", "response_format": "json", "temperature": "0"},
                         files={"file": (filename, data, mime)})
    if r.status_code >= 400:
        raise LLMError(f"groq whisper HTTP {r.status_code}: {r.text[:150]}")
    return r.json().get("text", "").strip()


async def transcribe(data: bytes, mime: str, filename: str, llm: LLM) -> tuple[str, str]:
    """Returns (transcript, method). Gemini first (strong on Hindi/Marathi), Groq Whisper next, OpenRouter last."""
    errors = []
    mime = (mime or "audio/ogg").split(";")[0].lower()
    wav: bytes | None = None
    if settings.gemini_key:
        try:
            if mime not in GEMINI_AUDIO_OK:
                wav = wav or await _ffmpeg_to_wav(data)
                payload, pm = wav, "audio/wav"
            else:
                payload, pm = data, mime
            out, _ = await llm.text("You are a transcription engine.", TRANSCRIBE_PROMPT,
                                    media=[(pm, payload)], providers=["gemini"])
            return ("" if out.strip() == "NO_SPEECH" else out.strip()), "gemini"
        except LLMError as e:
            errors.append(f"gemini: {e}")
    if settings.groq_key:
        try:
            return await _groq_whisper(data, filename or "audio.ogg", mime), "groq-whisper"
        except LLMError as e:
            errors.append(f"groq: {e}")
    if settings.openrouter_key:
        try:
            wav = wav or await _ffmpeg_to_wav(data)
            out, _ = await llm.text("You are a transcription engine.", TRANSCRIBE_PROMPT,
                                    media=[("audio/wav", wav)], providers=["openrouter"])
            return ("" if out.strip() == "NO_SPEECH" else out.strip()), "openrouter"
        except LLMError as e:
            errors.append(f"openrouter: {e}")
    raise LLMError("speech-to-text unavailable: " + ("; ".join(errors) or "set GEMINI_API_KEY or GROQ_API_KEY"))
