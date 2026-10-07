# ForwardCheck: "Is This Forward True?"

A WhatsApp bot and web app that checks forwarded messages. Send a message, screenshot, voice note, PDF or link.
It finds each claim, checks it against reliable sources only, and replies per claim with a verdict, the evidence, and a
plain-language explanation in English, Hindi or Marathi.

Verdicts: **Verified · False · Outdated · Partly supported · Cannot be confirmed**

> Status: Round 1 prototype for Hack On Track (FCRIT). Verified here: 39 automated tests, the HTTP/streaming path, OCR
> (English/Hindi/Marathi), PDF and URL ingestion, SSRF protection, and live evidence retrieval. **Not yet verified:**
> quality of verdicts from real free LLMs, voice-note transcription, and the live Twilio round trip. These need your
> API keys; see "First run" below.

## How it works

```
input ─► ingest ─► claims ─► evidence ─► judge ─► guardrail ─► reply
         text      LLM       fact-check   LLM      plain code    WhatsApp text
         image     JSON      API +        sees     cites real    or web cards
         audio     (≤5)      allow-listed  ONLY    evidence or
         PDF                 search +      the     becomes
         URL                 page fetch    evidence "cannot be confirmed"
```

* **Evidence-only judging.** The judge prompt forbids outside knowledge, and `app/judge.py::apply_guardrail` (plain code)
  downgrades any verdict that cites no real evidence item, whose label contradicts the cited sources' stance, or that
  says "Outdated" without a dated source.
* **Quotes come from retrieval, not the model.** The evidence text shown to the user is the passage we fetched, so the
  model cannot invent a quote or a link.
* **Reliable sources only.** `app/config.py::ALLOWLIST` (government, health bodies, IFCN fact-checkers, news agencies,
  plus any `*.gov.in`/`*.nic.in`). Everything else is dropped before judging.
* **Free-tier friendly.** One LLM wrapper (`app/llm.py`) tries Gemini → Groq → OpenRouter free models (auto-discovered),
  with backoff, JSON validation and one repair retry. Results are cached (24 h; 3 h for time-sensitive claims).
* **Long inputs.** PDFs and long articles are chunked; the chunks richest in checkable claims are analysed, and the top 5
  claims overall are checked (the user is told when more were found).
* **Safety.** Outbound fetches block private/loopback addresses and re-check every redirect (SSRF); the claim and evidence
  are treated as data in prompts (prompt-injection defence); uploads are size-limited; the API is rate-limited; the Twilio
  webhook verifies the request signature.

## First run

```bash
cd forwardcheck
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install tesseract ffmpeg          # already installed on this machine
cp .env.example .env                   # then add your keys
.venv/bin/uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

Hindi and Marathi OCR data is in `tessdata/` (`hin`, `mar`, `eng`), picked up automatically.

### Free keys (add what you can; at least one LLM key is required)
| Key | Where | Used for |
|---|---|---|
| `GEMINI_API_KEY` | aistudio.google.com | LLM + best Hindi/Marathi transcription and screenshot reading |
| `GROQ_API_KEY` | console.groq.com | fast LLM + Whisper fallback for voice |
| `OPENROUTER_API_KEY` | openrouter.ai | free-model fallback (models auto-discovered) |
| `GOOGLE_FACTCHECK_API_KEY` | Google Cloud console (enable "Fact Check Tools API") | published fact-checks, very fast, strongly recommended |
| `TAVILY_API_KEY` | tavily.com | better, faster search than the keyless fallback |

Check `http://localhost:8000/api/health` to see which are active. Free-tier limits change; check each provider's page.

### WhatsApp (Twilio sandbox)
1. Create a Twilio account, open **Messaging → Try it out → Send a WhatsApp message**, and join the sandbox from your phone.
2. Expose the server: `ngrok http 8000` (or any HTTPS tunnel). On college Wi-Fi use a mobile hotspot.
3. In `.env` set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `PUBLIC_BASE_URL=https://<your-ngrok-host>`.
4. In the sandbox settings set **When a message comes in** to `https://<your-ngrok-host>/whatsapp` (POST).
5. Message the sandbox number: `hi` shows help; `HINDI` / `MARATHI` / `ENGLISH` sets the reply language.
Judges who want to try it must first send the sandbox join code, so keep the web UI as the no-setup alternative.

## Tests and evaluation
```bash
.venv/bin/python -m pytest -q                      # 39 tests, no keys or network needed
.venv/bin/python scripts/eval.py tests/testset.csv # accuracy on YOUR labelled claims (see the script header)
```
Fill `tests/testset.csv` with 30-40 claims whose answers you verified from official sources, across all five verdicts,
input types and languages. Report those numbers in the pitch.

## Layout
```
app/main.py      FastAPI: web UI, /api/check, /api/check/stream (NDJSON), /whatsapp
app/ingest.py    text | image | audio | pdf | url -> clean text      app/media.py  OCR + speech-to-text
app/claims.py    claim extraction (LLM)        app/retrieve.py  evidence gathering
app/judge.py     judge + guardrail             app/pipeline.py  orchestration + cache
app/llm.py       provider fallback             app/reply.py     WhatsApp formatting   app/i18n.py  EN/HI/MR strings
web/index.html   single-file UI (record voice, upload, live progress, evidence cards)
```

## Known limits
* It verifies only what public, reliable sources can confirm; otherwise it says "Cannot be confirmed".
* Keyless web search is slow (~5-10 s per query) and sometimes returns nothing; the Fact Check API or Tavily keys fix this.
* Publication dates are extracted automatically and can be wrong; "Outdated" requires a dated source and the evidence
  panel shows each date so users can judge.
* Tesseract is weak on Devanagari, so when Indic text is detected a vision model is used if a key is available.
* The Twilio sandbox is for demos; production needs the official WhatsApp Business API.
