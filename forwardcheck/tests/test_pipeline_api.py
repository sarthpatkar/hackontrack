import json

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline, retrieve
from app.config import settings
from app.models import Claim, Label, Verdict
from tests.conftest import FakeLLM, ev


@pytest.fixture
def fake_search(monkeypatch):
    calls = {"n": 0}

    async def gather(claim, lang="en"):
        calls["n"] += 1
        return [ev()]
    monkeypatch.setattr(retrieve, "gather", gather)
    return calls


async def test_pipeline_end_to_end_and_cache(fake_search):
    llm = FakeLLM()
    res = await pipeline.run_check(llm, text="Govt gives Rs 5000 to every family")
    assert res.results[0].verdict.label == Label.FALSE
    assert res.results[0].verdict.evidence_ids == ["e1"] and not res.results[0].cached
    again = await pipeline.run_check(llm, text="Govt gives Rs 5000 to every family")
    assert again.results[0].cached and fake_search["n"] == 1 and llm.calls["verdict"] == 1


async def test_pipeline_no_evidence_means_cannot_confirm(monkeypatch):
    async def none(claim, lang="en"):
        return []
    monkeypatch.setattr(retrieve, "gather", none)
    res = await pipeline.run_check(FakeLLM(), text="Some unverifiable claim here")
    r = res.results[0]
    assert r.verdict.label == Label.CANNOT_BE_CONFIRMED and r.guardrail_note
    # a failed search must not poison the cache
    res2 = await pipeline.run_check(FakeLLM(), text="Some unverifiable claim here")
    assert not res2.results[0].cached


async def test_pipeline_no_claims():
    res = await pipeline.run_check(FakeLLM(claims=[]), text="Good morning everyone, have a nice day")
    assert res.results == [] and res.note


async def test_pipeline_caps_claims_and_reports(fake_search):
    many = [Claim(text=f"claim {i}", text_en=f"claim number {i} about thing {i}", check_worthiness=i) for i in range(9)]
    res = await pipeline.run_check(FakeLLM(claims=many), text="x " * 20)
    assert len(res.results) == settings.max_claims and "Found 9" in (res.note or "")
    assert res.results[0].claim.check_worthiness == 8  # most check-worthy first


async def test_language_override_and_detected(fake_search):
    res = await pipeline.run_check(FakeLLM(language="hi"), text="कुछ दावा")
    assert res.language == "hi"
    res = await pipeline.run_check(FakeLLM(language="hi"), text="कुछ दावा 2", lang_override="mr")
    assert res.language == "mr"
    res = await pipeline.run_check(FakeLLM(language="other"), text="something else")
    assert res.language == "en"


# ---------- HTTP API ----------
@pytest.fixture
def client(monkeypatch, fake_search):
    monkeypatch.setattr(main, "llm", FakeLLM())
    main._hits.clear()
    return TestClient(main.app)


def test_health_and_index(client):
    assert client.get("/api/health").json()["ok"] is True
    assert "ForwardCheck" in client.get("/").text


def test_api_check_text(client):
    r = client.post("/api/check", data={"text": "Govt gives Rs 5000 to every family"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["verdict"]["label"] == "FALSE"
    assert body["results"][0]["evidence"][0]["url"].startswith("https://pib.gov.in")


def test_api_check_validation_errors(client):
    assert client.post("/api/check", data={"text": ""}).status_code == 422
    r = client.post("/api/check", files={"file": ("x.exe", b"abc", "application/octet-stream")})
    assert r.status_code == 422
    r = client.post("/api/check", data={"url": "http://127.0.0.1:9/secret"})
    assert r.status_code == 422 and "private" in r.json()["error"]


def test_stream_events_in_order(client):
    with client.stream("POST", "/api/check/stream", data={"text": "Govt gives Rs 5000 to every family"}) as r:
        events = [json.loads(line) for line in r.iter_lines() if line]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "stage" and "claims" in kinds and "result" in kinds and kinds[-1] == "done"
    assert kinds.index("claims") < kinds.index("result") < kinds.index("done")


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    codes = [client.post("/api/check", data={"text": "claim text here"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---------- WhatsApp webhook ----------
def test_whatsapp_help_and_language(client, monkeypatch):
    monkeypatch.setattr(settings, "validate_twilio", False)
    r = client.post("/whatsapp", data={"From": "whatsapp:+911", "Body": "hi", "NumMedia": "0"})
    assert r.status_code == 200 and "<Message>" in r.text and "forwarded" in r.text.lower()
    r = client.post("/whatsapp", data={"From": "whatsapp:+911", "Body": "Marathi", "NumMedia": "0"})
    assert "मराठी" in r.text
    r = client.post("/whatsapp", data={"From": "whatsapp:+911", "Body": "Free money scheme!", "NumMedia": "0"})
    assert "मिनिट" in r.text  # acknowledgement is in the saved language (Marathi)


def test_whatsapp_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "validate_twilio", True)
    monkeypatch.setattr(settings, "twilio_token", "secret")
    r = client.post("/whatsapp", data={"From": "whatsapp:+911", "Body": "hi", "NumMedia": "0"})
    assert r.status_code == 403


async def test_whatsapp_background_sends_cards(monkeypatch, fake_search):
    sent = []

    async def fake_send(to, body):
        sent.append((to, body))
    monkeypatch.setattr(main, "send_whatsapp", fake_send)
    monkeypatch.setattr(main, "llm", FakeLLM())
    await main.process_whatsapp("whatsapp:+911", "Govt gives Rs 5000 to every family", None, "", None)
    assert sent and "❌" in sent[0][1] and "pib.gov.in" in sent[0][1]
