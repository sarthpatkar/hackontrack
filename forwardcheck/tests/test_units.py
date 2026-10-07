import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import ingest as ingest_mod
from app.config import source_info
from app.i18n import t
from app.judge import apply_guardrail
from app.llm import parse_json
from app.main import twilio_signature_ok
from app.models import ClaimResult, CheckResult, Label, Verdict
from app.net import FetchError, assert_public_url
from app.reply import format_card, format_messages
from app.retrieve import best_passage
from tests.conftest import FakeLLM, ev
from app.claims import chunk_text, pick_chunks


def test_parse_json_variants():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}
    assert parse_json('Sure! Here you go: {"a": [1,2]} hope that helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        parse_json("no json here")


# ---- guardrail: the core "no evidence, no verdict" promise
def test_guardrail_no_evidence_forces_cannot_confirm():
    v, note = apply_guardrail(Verdict(label=Label.FALSE, evidence_ids=["e1"]), [], "en")
    assert v.label == Label.CANNOT_BE_CONFIRMED and note


def test_guardrail_uncited_verdict_forced():
    v, note = apply_guardrail(Verdict(label=Label.VERIFIED, evidence_ids=[]), [ev()], "en")
    assert v.label == Label.CANNOT_BE_CONFIRMED and "no valid evidence" in note


def test_guardrail_invented_evidence_id_dropped():
    v, note = apply_guardrail(Verdict(label=Label.FALSE, evidence_ids=["e9"]), [ev()], "en")
    assert v.label == Label.CANNOT_BE_CONFIRMED


def test_guardrail_label_must_match_stance():
    v, _ = apply_guardrail(Verdict(label=Label.VERIFIED, evidence_ids=["e1"], evidence_stances={"e1": "contradicts"}),
                           [ev()], "en")
    assert v.label == Label.CANNOT_BE_CONFIRMED
    v, _ = apply_guardrail(Verdict(label=Label.FALSE, evidence_ids=["e1"], evidence_stances={"e1": "related"}),
                           [ev()], "en")
    assert v.label == Label.CANNOT_BE_CONFIRMED


def test_guardrail_outdated_needs_dated_source():
    v, _ = apply_guardrail(Verdict(label=Label.OUTDATED, evidence_ids=["e1"], evidence_stances={"e1": "contradicts"}),
                           [ev(date=None)], "en")
    assert v.label == Label.CANNOT_BE_CONFIRMED
    v, note = apply_guardrail(Verdict(label=Label.OUTDATED, evidence_ids=["e1"], evidence_stances={"e1": "contradicts"}),
                              [ev()], "en")
    assert v.label == Label.OUTDATED and note is None


def test_guardrail_forced_message_is_localised():
    v, _ = apply_guardrail(Verdict(label=Label.FALSE), [], "mr")
    assert v.what_is_wrong == t("no_evidence", "mr")


# ---- allowlist
def test_source_allowlist():
    assert source_info("https://www.who.int/news/x")[0] == "World Health Organization"
    assert source_info("https://factcheck.afp.com/x")[1] == "factcheck.afp.com"  # longest match beats parent domain
    assert source_info("https://pib.gov.in/PressReleasePage.aspx?PRID=1")[0] == "PIB"
    assert source_info("https://some.ministry.gov.in/a")  # any gov.in
    assert source_info("https://random-blog.com/health") is None
    assert source_info("https://evil-who.int.attacker.com/") is None
    assert source_info("https://notwho.int/") is None


# ---- SSRF protection
@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:8000/", "http://169.254.169.254/latest/meta-data",
                                 "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "ftp://example.com/"])
async def test_ssrf_blocked(url):
    with pytest.raises(FetchError):
        await assert_public_url(url)


# ---- retrieval helpers
def test_best_passage_prefers_overlap():
    text = ("The weather was fine today in the city. The Ministry clarified that no scheme gives Rs 5000 to every family. "
            "Sports results were announced later in the day.")
    p, rel = best_passage(text, "government gives Rs 5000 to every family")
    assert "5000" in p and rel > 0.3


def test_chunking_and_picking():
    big = "\n\n".join(f"Paragraph {i}. " + ("filler " * 200) for i in range(30))
    chunks = chunk_text(big)
    assert len(chunks) > 4 and all(len(c) <= 6500 for c in chunks)
    dense = "\n\n".join(["Govt will give Rs 5000 free scheme 100% ban " * 50] + ["filler " * 300] * 8)
    picked = pick_chunks(chunk_text(dense, 2000), 3)
    assert len(picked) == 3 and any("scheme" in c for c in picked)


# ---- WhatsApp reply
def _result(lang="en", label=Label.FALSE):
    from app.models import Claim
    c = Claim(id="c1", text="Govt gives Rs 5000.", text_en="Govt gives Rs 5000.")
    v = Verdict(label=label, what_is_wrong="Wrong amount " * 80, summary="Not true.", evidence_ids=["e1"],
                evidence_stances={"e1": "contradicts"})
    return CheckResult(input_type="text", language=lang, results=[ClaimResult(claim=c, verdict=v, evidence=[ev()])])


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_whatsapp_messages_fit_limit(lang):
    msgs = format_messages(_result(lang))
    assert msgs and all(len(m) <= 1600 for m in msgs)
    assert "https://pib.gov.in/x" in msgs[0]
    assert t("footer", lang) in msgs[-1]


def test_no_claims_message():
    assert format_messages(CheckResult(input_type="text", language="hi")) == [t("no_claims", "hi")]


# ---- Twilio signature (example from Twilio's own documentation)
def test_twilio_signature_known_vector(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "twilio_token", "12345")
    params = {"CallSid": "CA1234567890ABCDE", "Caller": "+12349013030", "Digits": "1234", "From": "+12349013030",
              "To": "+18005551212"}
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    assert twilio_signature_ok(url, params, "0/KCTR6DLpKmkAf8muzZqo1nDgQ=")
    assert not twilio_signature_ok(url, params, "bad")


# ---- ingestion
async def test_pdf_ingest():
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "The Ministry announced a new scheme on 1 March 2026.")
    data = doc.tobytes()
    out = await ingest_mod.ingest(FakeLLM(), file=(data, "a.pdf", "application/pdf"))
    assert out.input_type == "pdf" and "new scheme" in out.text


async def test_image_ocr_english():
    img = Image.new("RGB", (900, 220), "white")
    ImageDraw.Draw(img).text((20, 60), "Free laptops for all students", fill="black", font=ImageFont.load_default(size=48))
    buf = io.BytesIO(); img.save(buf, "PNG")
    out = await ingest_mod.ingest(FakeLLM(), file=(buf.getvalue(), "s.png", "image/png"))
    assert out.input_type == "image" and "laptops" in out.text.lower()


async def test_text_that_is_only_a_url_becomes_url_input(monkeypatch):
    async def fake(url):
        return ingest_mod.Ingested(text="article text " * 30, input_type="url", source_url=url)
    monkeypatch.setattr(ingest_mod, "url_to_text", fake)
    out = await ingest_mod.ingest(FakeLLM(), text="https://example.com/news/1")
    assert out.input_type == "url"
    out = await ingest_mod.ingest(FakeLLM(), text="Please read this and tell me if it is true " * 3 + "https://example.com/a")
    assert out.input_type == "text"


async def test_empty_and_bad_inputs():
    with pytest.raises(ingest_mod.IngestError):
        await ingest_mod.ingest(FakeLLM(), text="   ")
    with pytest.raises(ingest_mod.IngestError):
        await ingest_mod.ingest(FakeLLM(), file=(b"x", "a.exe", "application/octet-stream"))


def test_hindi_vs_marathi_detection():
    from app.lang import detect_indic
    assert detect_indic("सरकार प्रत्येक कुटुंबाला पाच हजार रुपये देणार आहे") == "mr"
    assert detect_indic("सरकार 1 नवंबर से हर परिवार को 5000 रुपये देगी") == "hi"
    assert detect_indic("Government gives free laptops") is None
    assert detect_indic("नमस्ते") is None  # no decisive markers


async def test_openrouter_refuses_paid_models():
    from app.llm import LLM
    from app.config import Settings
    s = Settings(openrouter_key="k", gemini_key="", groq_key="", openrouter_models=["some/paid-model"])
    llm = LLM(s)
    called = []

    async def boom(*a, **k):
        called.append(a)
        return "{}"
    llm._openai_style = boom
    import pytest
    from app.llm import LLMError
    with pytest.raises(LLMError):
        await llm._openrouter("s", "u", [], True)
    assert not called  # a non-:free model is never called
