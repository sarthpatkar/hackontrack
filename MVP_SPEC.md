# MVP Spec: "Is This Forward True?"
This is a design document, not code. Build starts at the 10:00 AM kickoff on Oct 15 from an empty repo (rulebook: no pre-built projects). Use this to move fast once the clock starts.

## 1. MVP scope

**Must have (the demo fails without these)**
- WhatsApp bot via Twilio sandbox
- Inputs: text, screenshot, voice note, PDF, URL
- Claim extraction (max 5 claims per message)
- Evidence retrieval from reliable sources
- Evidence-only judging with the 5 verdicts
- Reply per claim: verdict, what's wrong, evidence (source, date, link), plain-language summary
- Languages: English, Hindi, Marathi explanations; Hindi/Marathi/English voice and image input

**Should have**
- Web UI with the same pipeline (fallback if WhatsApp fails; also for judges to try)
- Claim cache for repeated forwards (be honest about it in the demo)
- "Checking..." status message

**Won't have (listed as future scope)**
- Voice replies, video input, dashboards/trends, official WhatsApp Business API, user accounts

## 2. User flow and acceptance criteria

| # | Input | Pass condition |
|---|---|---|
| 1 | Text message | Reply within ~60 s with 1-5 result cards |
| 2 | Screenshot (English/Hindi/Marathi text) | Text extracted, claims found, cards returned |
| 3 | Voice note (Hindi/Marathi/English) | Transcribed, language detected, cards returned |
| 4 | PDF (1-30 pages) | Top claims selected from the document, max 5 cards, says so if more exist |
| 5 | URL | Article text extracted; claims checked; article date shown |
| 6 | Unverifiable claim | Returns "Cannot be confirmed" with no fabricated source |
| 7 | Outdated claim | Returns "Outdated" and cites the newer source with its date |
| 8 | Non-claim text (greeting, opinion) | Replies politely that no checkable claim was found |
| 9 | Failure (API down, rate limit) | Replies with a friendly retry message; never crashes silently |

## 3. Planned repo layout
```
/app
  main.py            # FastAPI app: /whatsapp webhook, /api/check, /health
  config.py          # models, provider order, allowlist, limits (env + yaml)
  ingest/            # text.py image.py audio.py pdf.py url.py router.py
  claims.py          # claim extraction
  retrieve.py        # fact-check API + trusted search + page fetch
  judge.py           # evidence-only verdict + guardrail
  explain.py         # simple-language explanation + translation
  llm.py             # provider wrapper with fallback and JSON validation
  reply.py           # WhatsApp message formatting and splitting
  store.py           # SQLite: submissions, claims, evidence, verdicts, cache
/web                 # simple fallback UI
/tests               # test claims + evaluation script
README.md            # setup + architecture + how to run (needed for git check-ins)
```

## 4. Module contracts (agree these in the first hour)

```
ingest.router.to_text(message) -> {text, input_type, language?, source_date?, source_url?}
claims.extract(text, language) -> [Claim]            # max 5, ranked by check-worthiness
retrieve.evidence_for(claim)   -> [Evidence]         # 0..6 items
judge.verdict(claim, evidence) -> Verdict            # guardrail applied
explain.render(verdict, target_language) -> ReplyCard
reply.send(user, [ReplyCard])
```

### JSON schemas

**Claim**
```
{ "id": "c1",
  "text": "claim restated in one sentence, in original language",
  "text_en": "same claim in English (used for search)",
  "category": "health | government_scheme | news | finance | science | other",
  "time_sensitive": true,
  "claimed_date_hint": "2026-10 | null" }
```

**Evidence**
```
{ "id": "e1",
  "source_name": "PIB Fact Check",
  "domain": "pib.gov.in",
  "url": "https://...",
  "published_at": "2026-03-12 | null",
  "snippet": "exact quote or close excerpt, <= 300 chars",
  "stance_hint": "supports | contradicts | related" }
```

**Verdict**
```
{ "claim_id": "c1",
  "label": "VERIFIED | FALSE | OUTDATED | PARTLY_SUPPORTED | CANNOT_BE_CONFIRMED",
  "what_is_wrong": "one or two sentences naming the exact wrong or right part",
  "evidence_ids": ["e1", "e3"],
  "confidence": "high | medium | low",
  "reasoning_en": "short reasoning" }
```

## 5. Stage specs

### 5.1 Ingestion
- **Image:** run OCR (Tesseract with eng+hin+mar). If result is very short or low confidence, send the image to a free vision model. Return clean text.
- **Audio:** download Twilio media (needs auth), convert to a format the STT accepts (ffmpeg), transcribe with Whisper, detect language. Voice notes from WhatsApp arrive as OGG/Opus.
- **PDF:** extract text with PyMuPDF. If a page has no text (scanned), OCR it. For long PDFs: split into chunks, ask the LLM for the most check-worthy claims per chunk, then rank and keep the top 5.
- **URL:** fetch page, extract the main text and publish date. Handle failures (paywall/blocked) with a friendly message.
- **Text:** use as is. If it contains a URL, also fetch it.
- Detect language (script + LLM/lib); keep the original text for display.

### 5.2 Claim extraction (one LLM call)
Rules for the prompt:
- Return only checkable factual claims; skip opinions, greetings, questions, prayers
- One claim per item; make each self-contained (no "this" or "they")
- Provide an English version for search
- Flag time-sensitive claims
- Return JSON matching the Claim schema; max 5

### 5.3 Retrieval
1. Build 1-2 search queries from `text_en` (plain keywords + key numbers/names)
2. Query Google Fact Check Tools API for existing reviews
3. Query web search restricted to allowlisted domains
4. Fetch the top pages, extract the passage nearest to the claim, and the published date
5. Drop anything outside the allowlist; dedupe; keep up to 6 items
6. Return evidence with `stance_hint` left to the judge

Allowlist lives in config, grouped: government, health, fact-checkers, news agencies.

### 5.3a Cache (should-have)
Key = normalised `text_en` hash (exact match first; embedding similarity is optional). On a hit, reuse evidence and verdict but re-check if older than 24 h for time-sensitive claims. In the demo, say when a result came from cache.

### 5.4 Judge (one LLM call per claim)
Input: claim + evidence list only. The prompt forbids using outside knowledge.
Output: Verdict schema.

Label rules:
- VERIFIED: current reliable evidence supports the whole claim
- FALSE: reliable evidence contradicts it
- OUTDATED: evidence shows it was true earlier but a newer source changes it
- PARTLY_SUPPORTED: some parts hold, others don't; `what_is_wrong` must name each part
- CANNOT_BE_CONFIRMED: no relevant reliable evidence

### 5.5 Guardrail (plain code, not LLM)
- If evidence list is empty -> force CANNOT_BE_CONFIRMED
- If label != CANNOT_BE_CONFIRMED and `evidence_ids` is empty or contains ids not in the list -> force CANNOT_BE_CONFIRMED
- If label == OUTDATED and no cited evidence has a date -> downgrade to PARTLY_SUPPORTED or CANNOT_BE_CONFIRMED
- If JSON is invalid -> retry once with the validation error, then fall back to CANNOT_BE_CONFIRMED

### 5.6 Explain / translate
- Merge into the judge call where possible to save free-tier calls
- Output language = the language of the user's message (or user preference set by a command like "Hindi")
- Simple words, <= 2 short sentences for the summary; keep source names and links untranslated

### 5.7 Reply format (per claim, <= 1600 characters per Twilio message)
```
Claim: <short>
Verdict: <emoji + label in user's language>
What's wrong: <text>
Evidence:
1. <Source> (<date>): <short quote> <link>
2. ...
Summary: <1-2 sentences>
```
If a reply is too long, split by claim. Send a final line: "Reply HINDI / MARATHI / ENGLISH to change language."

## 6. WhatsApp / Twilio behaviour (things that bite)
- Sandbox: each tester must send the join code first; judges who want to try it need to do this, so also provide the web UI.
- Twilio webhooks expect a quick response (~15 s). Reply to the webhook immediately and send results with the Twilio REST API in a background task.
- Incoming media arrives as a URL (MediaUrl0) with MediaContentType; download with the Twilio credentials.
- Message body limit is 1600 characters; split long replies.
- Need a public HTTPS URL for the webhook (ngrok or a hosted service). Have a mobile hotspot ready in case venue Wi-Fi blocks it.

## 7. LLM wrapper (llm.py spec)
- `call(task, messages, schema)` where task in {extract, judge, explain, vision}
- Provider order per task from config (OpenRouter free model -> Gemini free -> Groq free)
- On 429/5xx/timeouts: backoff, then next provider
- Validate JSON against the schema; one repair retry
- Log provider, latency and failures (useful for the demo and Q&A)
- Temperature low (0-0.2) for extract/judge

## 8. Configuration and secrets (env vars)
`OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, GOOGLE_FACTCHECK_API_KEY, SEARCH_API_KEY (Tavily) `
Never commit keys. Add `.env` to `.gitignore` before the first push.

## 9. Test set (prepare before the event; test data is allowed prep)
Create 30-40 items as files + an answer key (CSV): `id, input_type, language, file, expected_label, notes`.
Cover:
- 5 labels x about 6 items each
- All 5 input types, including at least 3 Hindi and 3 Marathi voice notes and screenshots
- 3 non-claim messages
- 3 long-PDF cases
Use real, checkable claims whose answers you have verified yourself from official sources. Never put invented facts into the test set as ground truth.

Evaluation script (write during the event): runs the pipeline on every item, prints a confusion table, % with valid citations, average latency. Show these numbers in the pitch.

## 10. Build order with "done" criteria (matches the official git pushes)

| Push | Owner A (ingest) | Owner B (verify) | Owner C (WhatsApp/demo) | Done when |
|---|---|---|---|---|
| 1 PM | text/URL/PDF extractors | `llm.py`, claim extraction | FastAPI + Twilio echo | Message from phone round-trips; claims JSON printed |
| 5 PM | OCR, STT | retrieval + judge + guardrail | reply formatting, background send | A text claim returns a cited verdict on WhatsApp |
| 8 PM | PDF claim selection, language detect | five-label tuning, cache | web UI | All 5 inputs work end to end |
| 12 AM | Hindi/Marathi quality | explain/translate, test set run | error handling, README | Test report with accuracy numbers |
| 6:30 AM | fix extraction failures | fix judge/retrieval failures | hosting/hotspot test, demo script | 3 clean full runs in a row |
| 9:45 AM | freeze | freeze | record backup video, final README | Final push |

## 11. Scope-cut order (if behind)
1. Cache -> 2. Marathi voice (keep Marathi text) -> 3. Web UI polish -> 4. Scanned-PDF OCR -> 5. Multiple search queries per claim. Never cut: the guardrail, evidence display, or any of the 5 input types if you can help it.

## 12. Allowed prep before Oct 15 (no project code)
- [ ] Create free accounts and API keys; confirm each works with a one-line check in a throwaway terminal session (not part of the repo)
- [ ] Join the Twilio sandbox on every team phone
- [ ] Install Python 3.11, ffmpeg, Tesseract + Hindi/Marathi language packs, git, ngrok on every laptop
- [ ] Prepare the test set and answer key
- [ ] Shortlist the trusted-domain allowlist
- [ ] Write the prompt ideas on paper; write the real prompts in the event
- [ ] Agree the schemas above and the owner split
- [ ] Rehearse the 7-minute pitch with the test claims
- [ ] Student IDs, formal attire for Oct 16, hotspot, chargers

## 13. Definition of "MVP done" for the jury
- A live demo on a real phone through WhatsApp with at least one example of each input type and each verdict
- A visible evidence list on every verdict
- One unverifiable claim correctly answered "Cannot be confirmed"
- A test report with real numbers
- Backup: web UI and recorded video
